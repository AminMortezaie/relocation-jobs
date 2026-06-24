from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES
from relocation_jobs.v2.fetch import repo as fetch_repo
from relocation_jobs.v2.fetch.country_runner import run_country_fetch
from relocation_jobs.v2.fetch.pipeline import fetch_and_persist_company
from relocation_jobs.v2.scrape.board import fetch_ats_board

_fetch_lock = threading.Lock()
_fetch_thread: threading.Thread | None = None
_fetch_state: dict = {
    "running": False,
    "run_id": None,
    "country": None,
    "company": None,
    "ats_type": None,
    "file": None,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "concurrency": None,
    "result_line": None,
    "cancel_requested": False,
    "cancelled": False,
    "progress": {},
    "activity": {},
    "activity_log": [],
    "log": [],
    "review_jobs": None,
    "new_jobs_total": 0,
    "last_fetch_run": None,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _idle_fetch_status() -> dict:
    return {
        "running": False,
        "run_id": None,
        "country": None,
        "company": None,
        "ats_type": None,
        "file": None,
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "concurrency": None,
        "result_line": None,
        "cancel_requested": False,
        "cancelled": False,
        "progress": {},
        "activity": {},
        "activity_log": [],
        "log": [],
        "review_jobs": None,
        "new_jobs_total": 0,
        "last_fetch_run": None,
    }


def _status_from_row(row: dict | None) -> dict:
    if not row:
        return _idle_fetch_status()
    running = row.get("status") == "running"
    return {
        "running": running,
        "run_id": row.get("id"),
        "country": row.get("country"),
        "company": row.get("company_name"),
        "ats_type": row.get("ats_type"),
        "file": row.get("file"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "exit_code": row.get("exit_code"),
        "concurrency": row.get("concurrency"),
        "result_line": row.get("result_line"),
        "cancel_requested": bool(row.get("cancel_requested")),
        "cancelled": bool(row.get("cancelled")),
        "progress": dict(row.get("progress") or {}),
        "activity": dict(row.get("activity") or {}),
        "activity_log": list(row.get("activity_log") or []),
        "log": list(row.get("log") or []),
        "review_jobs": row.get("review_jobs"),
        "new_jobs_total": int(row.get("new_jobs") or 0),
        "last_fetch_run": None if running else row,
    }


def _memory_status() -> dict:
    with _fetch_lock:
        return {
            "running": bool(_fetch_state.get("running")),
            "run_id": _fetch_state.get("run_id"),
            "country": _fetch_state.get("country"),
            "company": _fetch_state.get("company"),
            "ats_type": _fetch_state.get("ats_type"),
            "file": _fetch_state.get("file"),
            "started_at": _fetch_state.get("started_at"),
            "finished_at": _fetch_state.get("finished_at"),
            "exit_code": _fetch_state.get("exit_code"),
            "concurrency": _fetch_state.get("concurrency"),
            "result_line": _fetch_state.get("result_line"),
            "cancel_requested": bool(_fetch_state.get("cancel_requested")),
            "cancelled": bool(_fetch_state.get("cancelled")),
            "progress": dict(_fetch_state.get("progress") or {}),
            "activity": dict(_fetch_state.get("activity") or {}),
            "activity_log": list(_fetch_state.get("activity_log") or []),
            "log": list(_fetch_state.get("log") or []),
            "review_jobs": _fetch_state.get("review_jobs"),
            "new_jobs_total": int(_fetch_state.get("new_jobs_total") or 0),
            "last_fetch_run": _fetch_state.get("last_fetch_run"),
        }


def _sync_live_to_db() -> None:
    with _fetch_lock:
        run_id = _fetch_state.get("run_id")
        if not run_id:
            return
        snapshot = {
            "progress": dict(_fetch_state.get("progress") or {}),
            "activity": dict(_fetch_state.get("activity") or {}),
            "activity_log": list(_fetch_state.get("activity_log") or []),
            "log": list(_fetch_state.get("log") or []),
            "cancel_requested": bool(_fetch_state.get("cancel_requested")),
            "new_jobs": int(_fetch_state.get("new_jobs_total") or 0),
            "result_line": _fetch_state.get("result_line"),
            "concurrency": _fetch_state.get("concurrency"),
        }
    fetch_repo.update_fetch_run_live(
        int(run_id),
        progress=snapshot["progress"],
        activity=snapshot["activity"],
        activity_log=snapshot["activity_log"],
        log=snapshot["log"],
        cancel_requested=snapshot["cancel_requested"],
        new_jobs=snapshot["new_jobs"],
        result_line=snapshot["result_line"],
    )


def _reap_zombie_fetch() -> None:
    should_finalize = False
    with _fetch_lock:
        if _fetch_state.get("running"):
            thread = _fetch_thread
            if thread is not None and thread.is_alive():
                return
            _fetch_state["running"] = False
            if _fetch_state.get("exit_code") is None:
                _fetch_state["exit_code"] = 1
                _fetch_state["log"].append("Fetch thread stopped unexpectedly")
            if not _fetch_state.get("finished_at"):
                _fetch_state["finished_at"] = _utc_now()
            should_finalize = bool(_fetch_state.get("run_id"))
    if should_finalize:
        _persist_fetch_run()
    with _fetch_lock:
        local_running = bool(_fetch_state.get("running"))
    if not local_running:
        fetch_repo.reap_orphan_running_fetch_runs()


def _persist_fetch_run() -> None:
    with _fetch_lock:
        run_id = _fetch_state.get("run_id")
        if not run_id:
            return
        payload = {
            "finished_at": _fetch_state.get("finished_at") or _utc_now(),
            "exit_code": _fetch_state.get("exit_code"),
            "cancelled": bool(_fetch_state.get("cancelled")),
            "new_jobs": int(_fetch_state.get("new_jobs_total") or 0),
            "concurrency": _fetch_state.get("concurrency"),
            "companies_done": int((_fetch_state.get("progress") or {}).get("current") or 0),
            "companies_total": int((_fetch_state.get("progress") or {}).get("total") or 0),
            "result_line": _fetch_state.get("result_line"),
            "progress": dict(_fetch_state.get("progress") or {}),
            "activity": dict(_fetch_state.get("activity") or {}),
            "activity_log": list(_fetch_state.get("activity_log") or []),
            "log": list(_fetch_state.get("log") or []),
        }
    row = fetch_repo.finalize_fetch_run(int(run_id), **payload)
    with _fetch_lock:
        _fetch_state["last_fetch_run"] = row
        _fetch_state["run_id"] = None


def build_fetch_status() -> dict:
    _reap_zombie_fetch()
    with _fetch_lock:
        if _fetch_state.get("running"):
            return _memory_status()
        if _fetch_state.get("last_fetch_run") is not None:
            return _memory_status()
    row = fetch_repo.get_running_fetch_run()
    if row:
        return _status_from_row(row)
    return _idle_fetch_status()


def fetch_is_running() -> bool:
    with _fetch_lock:
        if _fetch_state.get("running"):
            return True
    return fetch_repo.get_running_fetch_run() is not None


def request_fetch_cancel() -> tuple[bool, str | None]:
    with _fetch_lock:
        if not _fetch_state.get("running"):
            row = fetch_repo.get_running_fetch_run()
            if not row:
                return False, "No fetch is running"
            fetch_repo.request_fetch_run_cancel(int(row["id"]))
            return True, None
        _fetch_state["cancel_requested"] = True
        run_id = _fetch_state.get("run_id")
    if run_id:
        fetch_repo.request_fetch_run_cancel(int(run_id))
    _sync_live_to_db()
    return True, None


def _reset_fetch_state(
    *,
    user_id: int,
    country: str,
    file_name: str,
    concurrency: int,
    company: str | None = None,
    ats_type: str | None = None,
) -> int:
    global _fetch_thread
    _fetch_thread = None
    started_at = _utc_now()
    row = fetch_repo.create_fetch_run(
        user_id=user_id,
        country=country,
        company_name=company,
        file_name=file_name,
        concurrency=concurrency,
        ats_type=ats_type,
        started_at=started_at,
    )
    run_id = int(row["id"])
    _fetch_state.clear()
    _fetch_state.update({
        "running": True,
        "run_id": run_id,
        "country": country,
        "company": company,
        "ats_type": ats_type,
        "file": file_name,
        "concurrency": concurrency,
        "started_at": started_at,
        "finished_at": None,
        "exit_code": None,
        "result_line": None,
        "cancel_requested": False,
        "cancelled": False,
        "progress": {"current": 0, "total": 0, "company": None, "status": ""},
        "activity": {"message": "", "detail": ""},
        "activity_log": [],
        "log": [],
        "review_jobs": None,
        "new_jobs_total": 0,
        "last_fetch_run": None,
    })
    _sync_live_to_db()
    return run_id


def _on_country_progress(progress: dict) -> None:
    with _fetch_lock:
        _fetch_state["progress"] = dict(progress)
    _sync_live_to_db()


def _append_log(line: str) -> None:
    with _fetch_lock:
        _fetch_state["log"].append(line)
    _sync_live_to_db()


def _country_fetch_worker(
    country_key: str,
    *,
    run_id: int,
    skip_filled: bool,
    ats_type: str | None,
) -> None:
    exit_code = 1
    cancelled = False
    new_jobs_total = 0
    companies_done = 0
    try:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx is not installed")
        import httpx

        async def _run():
            nonlocal new_jobs_total, companies_done, cancelled
            async with httpx.AsyncClient() as client:
                return await run_country_fetch(
                    client,
                    country_key,
                    run_id=run_id,
                    skip_filled=skip_filled,
                    ats_type=ats_type,
                    on_progress=_on_country_progress,
                    on_log=_append_log,
                )

        new_jobs_total, companies_done, cancelled = asyncio.run(_run())
        exit_code = 130 if cancelled else 0
    except Exception as exc:
        _append_log(f"Error: {exc}")
        exit_code = 1
    finally:
        finish_line = None
        with _fetch_lock:
            if cancelled:
                _fetch_state["cancelled"] = True
                _fetch_state["exit_code"] = 130
                finish_line = "Cancelled by user"
            else:
                _fetch_state["exit_code"] = exit_code
                finish_line = "Finished (exit 0)" if exit_code == 0 else f"Finished (exit {exit_code})"
            _fetch_state["new_jobs_total"] = new_jobs_total
            prog = dict(_fetch_state.get("progress") or {})
            total = int(prog.get("total") or 0)
            if total > 0 and not cancelled:
                _fetch_state["progress"] = {**prog, "current": total, "status": "done"}
            if finish_line:
                _fetch_state["log"].append(finish_line)
            _fetch_state["result_line"] = (
                f"Done {companies_done} companies, {new_jobs_total} new jobs"
                if exit_code == 0
                else finish_line
            )
            _fetch_state["running"] = False
            _fetch_state["finished_at"] = _utc_now()
        _sync_live_to_db()
        _persist_fetch_run()


def start_country_fetch(
    *,
    user_id: int,
    country_key: str,
    skip_filled: bool = False,
    ats_type: str | None = None,
    concurrency: int = 1,
) -> int:
    global _fetch_thread
    _reap_zombie_fetch()
    if fetch_is_running():
        raise RuntimeError("A fetch is already running")
    workers = max(1, min(int(concurrency), 64))
    file_name = COUNTRY_ARCHIVE_FILENAMES[country_key]
    with _fetch_lock:
        run_id = _reset_fetch_state(
            user_id=user_id,
            country=country_key,
            file_name=file_name,
            concurrency=workers,
            ats_type=ats_type,
        )
        _fetch_thread = threading.Thread(
            target=_country_fetch_worker,
            args=(country_key,),
            kwargs={
                "run_id": run_id,
                "skip_filled": skip_filled,
                "ats_type": ats_type,
            },
            daemon=True,
        )
        _fetch_thread.start()
    return run_id


async def run_single_company_fetch_async(
    country_key: str,
    company_name: str,
    *,
    fetch_run_id: int | None = None,
) -> tuple[str, int]:
    if not HTTPX_AVAILABLE:
        raise RuntimeError("httpx is not installed")
    import httpx

    async with httpx.AsyncClient() as client:
        return await fetch_and_persist_company(
            client,
            country_key,
            company_name,
            fetch_board=fetch_ats_board,
            fetch_run_id=fetch_run_id,
        )


def run_single_company_fetch(
    country_key: str,
    company_name: str,
    *,
    fetch_run_id: int | None = None,
) -> tuple[str, int]:
    return asyncio.run(
        run_single_company_fetch_async(
            country_key,
            company_name,
            fetch_run_id=fetch_run_id,
        )
    )
