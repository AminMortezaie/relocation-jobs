"""Scrape subprocess orchestration and fetch run state."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from relocation_jobs.catalog_db import touch_country_meta
from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, PROJECT_ROOT, SUPPORTED_COUNTRIES
from relocation_jobs.db import record_fetch_run
from relocation_jobs.services.company_service import touch_company_fetch_time
from relocation_jobs.web import fetch_state
from relocation_jobs.web.fetch_state import _fetch_lock, _fetch_state

ROOT = PROJECT_ROOT

_TOTAL_RE = re.compile(r"\((\d+)\s+to process")


def _reap_zombie_fetch() -> None:
    """Clear stale running flag when the scrape thread has exited."""
    should_persist = False
    with _fetch_lock:
        if not _fetch_state.get("running"):
            return
        if fetch_state._fetch_thread is None:
            return
        if fetch_state._fetch_thread.is_alive():
            return
        _fetch_state["running"] = False
        if _fetch_state.get("exit_code") is None:
            _fetch_state["exit_code"] = 1
            _fetch_state["log"].append("Fetch thread stopped unexpectedly")
        if not _fetch_state.get("finished_at"):
            _fetch_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        should_persist = not _fetch_state.get("fetch_run_recorded")
    if should_persist:
        _persist_fetch_run()


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


def _reset_fetch_run_state(*, country, company, file_name, concurrency, user_id=None) -> None:
    fetch_state._fetch_thread = None
    _fetch_state["running"] = True
    _fetch_state["country"] = country
    _fetch_state["company"] = company
    _fetch_state["file"] = file_name
    _fetch_state["concurrency"] = concurrency
    _fetch_state["user_id"] = user_id
    _fetch_state["fetch_run_recorded"] = False
    _fetch_state["last_fetch_run"] = None
    _fetch_state["started_at"] = datetime.now(timezone.utc).isoformat()
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


def _build_fetch_run_snapshot() -> dict | None:
    with _fetch_lock:
        if _fetch_state.get("fetch_run_recorded"):
            return None
        user_id = _fetch_state.get("user_id")
        country = _fetch_state.get("country")
        started_at = _fetch_state.get("started_at")
        finished_at = _fetch_state.get("finished_at")
        if not user_id or not country or not started_at or not finished_at:
            return None
        prog = _fetch_state.get("progress") or {}
        _fetch_state["fetch_run_recorded"] = True
        return {
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
        }


def _persist_fetch_run() -> dict | None:
    snapshot = _build_fetch_run_snapshot()
    if not snapshot:
        return None
    try:
        row = record_fetch_run(**snapshot)
    except Exception:
        return None
    with _fetch_lock:
        _fetch_state["last_fetch_run"] = row
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


def _build_scrape_cmd(
    country: str,
    skip_filled: bool,
    concurrency: int,
    *,
    company: str | None = None,
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
    proc.terminate()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2.0)


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
        )
        env = {**os.environ, "PANEL_SCRAPE_CHILD": "1"}
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(ROOT),
        )
        with _fetch_lock:
            _fetch_state["process"] = proc

        if proc.stdout is not None:
            for line in proc.stdout:
                text = line.rstrip("\n")
                if _handle_scrape_ipc_line(text):
                    continue
                _log(text)
        exit_code = proc.wait()
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
) -> None:
    import threading

    workers = _fetch_state["concurrency"]
    fetch_state._fetch_thread = threading.Thread(
        target=_run_scrape,
        args=(country, skip_filled, workers),
        kwargs={"company": company},
        daemon=True,
    )
    fetch_state._fetch_thread.start()
