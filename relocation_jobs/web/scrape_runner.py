"""Scrape subprocess orchestration and fetch run state."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone

from relocation_jobs.catalog_db import touch_country_meta
from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, PROJECT_ROOT, SUPPORTED_COUNTRIES
from relocation_jobs.db import (
    create_fetch_run,
    finalize_fetch_run,
    fetch_status_from_row,
    get_running_fetch_run,
    idle_fetch_status,
    reap_orphan_running_fetch_runs,
    update_fetch_run_live,
)
from relocation_jobs.services.company_service import touch_company_fetch_time
from relocation_jobs.web import fetch_state
from relocation_jobs.web.fetch_state import _fetch_lock, _fetch_state

ROOT = PROJECT_ROOT

_TOTAL_RE = re.compile(r"\((\d+)\s+to process")


def _fetch_status_from_memory() -> dict:
    prog = _fetch_state.get("progress") or {}
    return {
        "running": bool(_fetch_state.get("running")),
        "run_id": _fetch_state.get("run_id"),
        "country": _fetch_state["country"],
        "company": _fetch_state.get("company"),
        "ats_type": _fetch_state.get("ats_type"),
        "file": _fetch_state["file"],
        "started_at": _fetch_state["started_at"],
        "finished_at": _fetch_state["finished_at"],
        "exit_code": _fetch_state["exit_code"],
        "concurrency": _fetch_state.get("concurrency"),
        "result_line": _fetch_state.get("result_line"),
        "cancel_requested": _fetch_state.get("cancel_requested", False),
        "cancelled": _fetch_state.get("cancelled", False),
        "progress": dict(prog),
        "activity": dict(_fetch_state.get("activity") or {}),
        "activity_log": list(_fetch_state.get("activity_log") or []),
        "log": list(_fetch_state["log"]),
        "review_jobs": _fetch_state.get("review_jobs"),
        "new_jobs_total": int(_fetch_state.get("new_jobs_total") or 0),
        "last_fetch_run": _fetch_state.get("last_fetch_run"),
    }


def build_fetch_status_payload() -> dict:
    """Return live fetch status — memory when this process is scraping, else Postgres."""
    _reap_zombie_fetch()
    with _fetch_lock:
        if _fetch_state.get("running"):
            return _fetch_status_from_memory()
        if _fetch_state.get("last_fetch_run") is not None:
            return _fetch_status_from_memory()
    row = get_running_fetch_run()
    if row:
        return fetch_status_from_row(row)
    return idle_fetch_status()


def fetch_is_running() -> bool:
    with _fetch_lock:
        if _fetch_state.get("running"):
            return True
    return get_running_fetch_run() is not None


def _sync_fetch_run() -> None:
    run_id = _fetch_state.get("run_id")
    if not run_id:
        return
    prog = _fetch_state.get("progress") or {}
    try:
        update_fetch_run_live(
            int(run_id),
            progress=dict(prog),
            activity=dict(_fetch_state.get("activity") or {}),
            activity_log=list(_fetch_state.get("activity_log") or []),
            log=list(_fetch_state["log"]),
            review_jobs=_fetch_state.get("review_jobs"),
            cancel_requested=bool(_fetch_state.get("cancel_requested")),
            new_jobs=int(_fetch_state.get("new_jobs_total") or 0),
            result_line=_fetch_state.get("result_line"),
            concurrency=_fetch_state.get("concurrency"),
        )
    except Exception:
        pass


def _reap_zombie_fetch() -> None:
    """Clear stale running flag when the scrape thread has exited; reap DB orphans."""
    should_finalize = False
    with _fetch_lock:
        if _fetch_state.get("running"):
            thread = fetch_state._fetch_thread
            if thread is None:
                return
            if thread.is_alive():
                return
            _fetch_state["running"] = False
            if _fetch_state.get("exit_code") is None:
                _fetch_state["exit_code"] = 1
                _fetch_state["log"].append("Fetch thread stopped unexpectedly")
            if not _fetch_state.get("finished_at"):
                _fetch_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            should_finalize = bool(_fetch_state.get("run_id"))
    if should_finalize:
        _persist_fetch_run()

    with _fetch_lock:
        local_running = bool(_fetch_state.get("running"))
    if not local_running:
        reap_orphan_running_fetch_runs()


def _should_cancel_fetch() -> bool:
    with _fetch_lock:
        return bool(_fetch_state.get("cancel_requested"))


def _on_scrape_progress(info: dict) -> None:
    with _fetch_lock:
        _fetch_state["progress"] = {
            "current": int(info.get("current") or 0),
            "total": int(info.get("total") or 0),
            "company": info.get("company"),
            "status": info.get("status") or "",
        }


def _on_scrape_review(info: dict) -> None:
    with _fetch_lock:
        _fetch_state["review_jobs"] = {
            "included": list(info.get("included") or []),
            "filtered": list(info.get("filtered") or []),
        }


def _reset_fetch_run_state(*, country, company, file_name, concurrency, user_id=None, ats_type=None) -> None:
    fetch_state._fetch_thread = None
    started_at = datetime.now(timezone.utc).isoformat()
    row = create_fetch_run(
        user_id=int(user_id),
        country=country,
        company_name=company,
        file_name=file_name,
        concurrency=concurrency,
        ats_type=ats_type,
        started_at=started_at,
    )
    _fetch_state["run_id"] = row.get("id")
    _fetch_state["running"] = True
    _fetch_state["country"] = country
    _fetch_state["company"] = company
    _fetch_state["ats_type"] = ats_type
    _fetch_state["file"] = file_name
    _fetch_state["concurrency"] = concurrency
    _fetch_state["user_id"] = user_id
    _fetch_state["last_fetch_run"] = None
    _fetch_state["started_at"] = started_at
    _fetch_state["finished_at"] = None
    _fetch_state["exit_code"] = None
    _fetch_state["result_line"] = None
    _fetch_state["cancel_requested"] = False
    _fetch_state["cancelled"] = False
    _fetch_state["progress"] = {"current": 0, "total": 0, "company": None, "status": ""}
    _fetch_state["review_jobs"] = None
    _fetch_state["activity"] = {"message": "", "detail": ""}
    _fetch_state["activity_log"].clear()
    _fetch_state["activity_touch_company"] = None
    _fetch_state["new_jobs_total"] = 0
    _fetch_state["log"].clear()
    if company:
        _push_fetch_activity(f"Fetching {company}…")
    else:
        _push_fetch_activity("Starting country fetch…")
    _sync_fetch_run()


def _build_fetch_run_snapshot() -> dict | None:
    run_id = _fetch_state.get("run_id")
    user_id = _fetch_state.get("user_id")
    country = _fetch_state.get("country")
    started_at = _fetch_state.get("started_at")
    finished_at = _fetch_state.get("finished_at")
    if not run_id or not user_id or not country or not started_at or not finished_at:
        return None
    prog = _fetch_state.get("progress") or {}
    return {
        "run_id": int(run_id),
        "user_id": int(user_id),
        "country": str(country),
        "company_name": _fetch_state.get("company"),
        "started_at": str(started_at),
        "finished_at": str(finished_at),
        "exit_code": _fetch_state.get("exit_code"),
        "cancelled": bool(_fetch_state.get("cancelled")),
        "new_jobs": int(_fetch_state.get("new_jobs_total") or 0),
        "concurrency": _fetch_state.get("concurrency"),
        "companies_done": int(prog.get("current") or 0) or None,
        "companies_total": int(prog.get("total") or 0) or None,
        "result_line": _fetch_state.get("result_line"),
        "progress": dict(prog),
        "activity": dict(_fetch_state.get("activity") or {}),
        "activity_log": list(_fetch_state.get("activity_log") or []),
        "log": list(_fetch_state["log"]),
        "review_jobs": _fetch_state.get("review_jobs"),
    }


def _persist_fetch_run() -> dict | None:
    snapshot = _build_fetch_run_snapshot()
    if not snapshot:
        return None
    try:
        row = finalize_fetch_run(
            snapshot["run_id"],
            finished_at=snapshot["finished_at"],
            exit_code=snapshot["exit_code"],
            cancelled=snapshot["cancelled"],
            new_jobs=snapshot["new_jobs"],
            concurrency=snapshot["concurrency"],
            companies_done=snapshot["companies_done"],
            companies_total=snapshot["companies_total"],
            result_line=snapshot["result_line"],
            progress=snapshot["progress"],
            activity=snapshot["activity"],
            activity_log=snapshot["activity_log"],
            log=snapshot["log"],
            review_jobs=snapshot["review_jobs"],
        )
    except Exception:
        return None
    with _fetch_lock:
        _fetch_state["last_fetch_run"] = row
        _fetch_state["run_id"] = None
    return row


def _push_fetch_activity(message: str, detail: str = "") -> None:
    message = (message or "").strip()
    if not message:
        return
    entry = {"message": message, "detail": (detail or "").strip()}
    _fetch_state["activity"] = entry
    if not _fetch_state["activity_log"] or _fetch_state["activity_log"][-1] != entry:
        _fetch_state["activity_log"].append(entry)


def _activity_from_scrape_line(text: str) -> dict | None:
    """Turn scraper console lines into user-facing fetch steps."""
    t = (text or "").strip()
    if not t or t.startswith("@@"):
        return None
    if t.startswith("Finished ") or t.startswith("Done "):
        return None

    m = re.match(r"Fetching (.+)$", t)
    if m:
        return {"message": f"Fetching {m.group(1).strip()}…", "detail": ""}

    m = re.match(r"Detected:\s*(\S+)\s*→\s*(.+)", t)
    if m:
        return {"message": f"Detected {m.group(1)} board", "detail": m.group(2).strip()}

    m = re.match(r"Known(?: override)?:\s*(\S+)\s*→\s*(.+)", t)
    if m:
        return {"message": f"Using {m.group(1)} board", "detail": m.group(2).strip()}

    if "Detecting ATS via Playwright" in t:
        return {"message": "Detecting job board from careers page…", "detail": "Playwright"}

    if "No ATS detected, using generic" in t:
        return {"message": "No job board detected", "detail": "Loading careers page directly"}

    m = re.match(r"TeamTailor HTML board:\s*(\d+) role", t)
    if m:
        return {"message": f"Loaded {m.group(1)} roles from TeamTailor", "detail": ""}

    m = re.match(r"Loading TeamTailor page (\d+)…", t)
    if m:
        return {"message": f"Loading TeamTailor page {m.group(1)}", "detail": ""}

    if t.endswith(" API") or " API error" in t:
        return None

    for label in (
        "Greenhouse", "Lever", "Recruitee", "Ashby", "Personio",
        "SmartRecruiters", "Workable", "Join", "Deel", "bol careers",
    ):
        if f"{label} error" in t:
            return {"message": f"{label} request failed", "detail": t}

    if "Playwright error" in t:
        return {"message": "Careers page load failed", "detail": t}

    if " — enriched " in t and "job(s)" in t:
        m = re.search(r"enriched (\d+) job", t)
        if m:
            return {"message": f"Checking visa/relocation on {m.group(1)} roles", "detail": ""}

    if " — " in t and t[0] == "[":
        return None

    return None


def _handle_scrape_ipc_line(line: str) -> bool:
    if line.startswith("@@PROGRESS@@"):
        try:
            data = json.loads(line[len("@@PROGRESS@@"):])
            company = data.get("company")
            status = data.get("status") or ""
            country = None
            with _fetch_lock:
                _fetch_state["progress"] = {
                    "current": int(data.get("current") or 0),
                    "total": int(data.get("total") or 0),
                    "company": company,
                    "status": status,
                }
                if status == "done" and "new_jobs" in data:
                    _fetch_state["new_jobs_total"] = int(
                        _fetch_state.get("new_jobs_total") or 0
                    ) + int(data.get("new_jobs") or 0)
                country = _fetch_state.get("country")
                should_touch = (
                    status == "fetching"
                    and company
                    and country
                    and _fetch_state.get("activity_touch_company") != company
                )
                if should_touch:
                    _fetch_state["activity_touch_company"] = company
            if should_touch:
                try:
                    touch_company_fetch_time(country, company)
                except (LookupError, ValueError):
                    pass
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        _sync_fetch_run()
        return True
    if line.startswith("@@REVIEW@@"):
        try:
            data = json.loads(line[len("@@REVIEW@@"):])
            with _fetch_lock:
                _fetch_state["review_jobs"] = {
                    "included": list(data.get("included") or []),
                    "filtered": list(data.get("filtered") or []),
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        _sync_fetch_run()
        return True
    if line.startswith("@@ACTIVITY@@"):
        try:
            data = json.loads(line[len("@@ACTIVITY@@"):])
            with _fetch_lock:
                _push_fetch_activity(
                    str(data.get("message") or ""),
                    str(data.get("detail") or ""),
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        _sync_fetch_run()
        return True
    return False


def _log(line: str) -> None:
    text = line.rstrip()
    if not text:
        return
    with _fetch_lock:
        _fetch_state["log"].append(text)
        activity = _activity_from_scrape_line(text)
        if activity:
            _push_fetch_activity(activity["message"], activity.get("detail", ""))
        if " — " in text and (text.startswith("[") or text.startswith("Done ")):
            _fetch_state["result_line"] = text
        m_total = _TOTAL_RE.search(text)
        if m_total:
            _fetch_state["progress"]["total"] = int(m_total.group(1))
    _sync_fetch_run()


def _build_scrape_cmd(
    country: str,
    skip_filled: bool,
    concurrency: int,
    *,
    company: str | None = None,
    ats_type: str | None = None,
) -> list[str]:
    if country not in SUPPORTED_COUNTRIES:
        raise LookupError(f"Unknown country: {country}")
    cmd = [
        sys.executable,
        "-m",
        "relocation_jobs.scrape_jobs",
        "--country",
        country,
    ]
    if ats_type:
        cmd.extend(["--ats", ats_type])
    if skip_filled and not company:
        cmd.append("--skip-filled")
    workers = 1 if company else max(1, min(int(concurrency), 64))
    if workers <= 1:
        cmd.append("--serial")
    else:
        cmd.extend(["--workers", str(workers)])
    if company:
        cmd.append(company)
    return cmd


def _terminate_scrape_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    terminated = False
    pid = getattr(proc, "pid", None)
    if pid:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            terminated = True
        except (ProcessLookupError, PermissionError, OSError):
            pass
    if not terminated:
        proc.terminate()
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        if pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
        else:
            proc.kill()
        proc.wait(timeout=2.0)


def request_fetch_cancel() -> tuple[bool, str | None]:
    """Request cancellation of the active fetch and terminate the scrape subprocess."""
    proc = None
    run_id = None
    in_memory = False
    with _fetch_lock:
        in_memory = bool(_fetch_state.get("running"))
        run_id = _fetch_state.get("run_id")
        proc = _fetch_state.get("process")
        _fetch_state["cancel_requested"] = True

    if not in_memory:
        row = get_running_fetch_run()
        if not row:
            with _fetch_lock:
                _fetch_state["cancel_requested"] = False
            return False, "No fetch is running"
        run_id = run_id or row.get("id")
        with _fetch_lock:
            if not _fetch_state.get("running"):
                _fetch_state["running"] = True
                _fetch_state["country"] = row.get("country")
                _fetch_state["company"] = row.get("company_name")
                _fetch_state["started_at"] = row.get("started_at")
                _fetch_state["run_id"] = run_id

    if run_id:
        try:
            update_fetch_run_live(int(run_id), cancel_requested=True)
        except (TypeError, ValueError):
            pass

    _terminate_scrape_process(proc)

    thread = fetch_state._fetch_thread
    if proc is None and (thread is None or not thread.is_alive()) and run_id:
        finished_at = datetime.now(timezone.utc).isoformat()
        with _fetch_lock:
            prog = dict(_fetch_state.get("progress") or {})
            new_jobs = int(_fetch_state.get("new_jobs_total") or 0)
            concurrency = _fetch_state.get("concurrency")
            activity = dict(_fetch_state.get("activity") or {})
            activity_log = list(_fetch_state.get("activity_log") or [])
            _fetch_state["exit_code"] = 130
            _fetch_state["cancelled"] = True
            _fetch_state["running"] = False
            _fetch_state["finished_at"] = finished_at
            log = list(_fetch_state["log"])
            if "Cancelled by user" not in log:
                _log("Cancelled by user")
                log = list(_fetch_state["log"])
        try:
            finalize_fetch_run(
                int(run_id),
                finished_at=finished_at,
                exit_code=130,
                cancelled=True,
                new_jobs=new_jobs,
                concurrency=concurrency,
                companies_done=int(prog.get("current") or 0) or None,
                companies_total=int(prog.get("total") or 0) or None,
                progress=prog,
                activity=activity,
                activity_log=activity_log,
                log=log,
            )
        except Exception:
            pass
    return True, None


class _LogWriter:
    """Capture scraper stdout into the fetch log line-by-line."""

    def write(self, s: str) -> None:
        if not s:
            return
        for line in s.splitlines():
            _log(line)

    def flush(self) -> None:
        pass


def _run_scrape(
    country: str,
    skip_filled: bool,
    concurrency: int,
    *,
    company: str | None = None,
    ats_type: str | None = None,
) -> None:
    proc: subprocess.Popen | None = None
    exit_code: int | None = None
    try:
        if company:
            concurrency = 1
            with _fetch_lock:
                _fetch_state["progress"]["total"] = 1
        else:
            concurrency = max(1, min(int(concurrency), 64))
        _fetch_state["concurrency"] = concurrency

        filename = COUNTRY_ARCHIVE_FILENAMES.get(country)
        if company:
            _log(f"Fetching {company}")
        elif ats_type:
            _log(f"Fetching {ats_type} companies in {filename} ({concurrency} workers)")
        else:
            _log(f"Fetching all companies in {filename} ({concurrency} workers)")

        if not HTTPX_AVAILABLE:
            _log("Error: httpx is not installed. Run: pip install httpx")
            _fetch_state["exit_code"] = 1
            return

        cmd = _build_scrape_cmd(
            country,
            skip_filled and not company,
            concurrency,
            company=company,
            ats_type=ats_type,
        )
        env = {**os.environ, "PANEL_SCRAPE_CHILD": "1"}
        run_id = _fetch_state.get("run_id")
        if run_id:
            env["PANEL_FETCH_RUN_ID"] = str(run_id)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(ROOT),
            start_new_session=True,
        )
        with _fetch_lock:
            _fetch_state["process"] = proc

        if proc.stdout is not None:
            for line in proc.stdout:
                if _should_cancel_fetch():
                    _terminate_scrape_process(proc)
                    break
                text = line.rstrip("\n")
                if _handle_scrape_ipc_line(text):
                    continue
                _log(text)
        if _should_cancel_fetch() and proc is not None and proc.poll() is None:
            _terminate_scrape_process(proc)
        exit_code = proc.wait() if proc is not None else exit_code
    except LookupError as e:
        _log(f"Error: {e}")
        exit_code = 1
        _log("Finished (exit 1)")
    except Exception as e:
        _log(f"Error: {e}")
        exit_code = 1
        _log("Finished (exit 1)")
    finally:
        with _fetch_lock:
            cancelled = bool(_fetch_state.get("cancel_requested"))
            if cancelled:
                _fetch_state["exit_code"] = 130
                _log("Cancelled by user")
            elif exit_code == 0:
                _fetch_state["exit_code"] = 0
                _log("Finished (exit 0)")
            elif exit_code is not None:
                _fetch_state["exit_code"] = exit_code
                _log(f"Finished (exit {exit_code})")
            elif _fetch_state.get("exit_code") is None:
                _fetch_state["exit_code"] = 1

            prog = _fetch_state.get("progress") or {}
            total = int(prog.get("total") or 0)
            if total > 0 and not cancelled:
                _fetch_state["progress"] = {
                    **prog,
                    "current": total,
                    "status": "done",
                }
            if company and _fetch_state.get("review_jobs") is None:
                _fetch_state["review_jobs"] = {"included": [], "filtered": []}
            if cancelled:
                _fetch_state["cancelled"] = True
            _fetch_state["running"] = False
            _fetch_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _fetch_state["process"] = None
            country_key = _fetch_state.get("country")
            new_jobs_total = int(_fetch_state.get("new_jobs_total") or 0)
        if country_key and country_key in SUPPORTED_COUNTRIES:
            try:
                touch_country_meta(country_key, last_fetch_new_jobs=new_jobs_total)
            except Exception:
                pass
        _persist_fetch_run()
        if proc is not None and proc.poll() is None:
            _terminate_scrape_process(proc)
def _start_scrape_thread(
    country: str,
    skip_filled: bool,
    concurrency: int,
    *,
    company: str | None = None,
    ats_type: str | None = None,
) -> None:
    workers = _fetch_state["concurrency"]
    fetch_state._fetch_thread = threading.Thread(
        target=_run_scrape,
        args=(country, skip_filled, workers),
        kwargs={"company": company, "ats_type": ats_type},
        daemon=True,
    )
    fetch_state._fetch_thread.start()
