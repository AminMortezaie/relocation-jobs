from __future__ import annotations

import threading
from datetime import datetime, timezone

from relocation_jobs.fetch import repo as fetch_repo

_fetch_lock = threading.RLock()
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def idle_fetch_status() -> dict:
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


def status_from_row(row: dict | None) -> dict:
    if not row:
        return idle_fetch_status()
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


def memory_status() -> dict:
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


def sync_live_to_db() -> None:
    with _fetch_lock:
        run_id = _fetch_state.get("run_id")
        if not run_id:
            return
        snapshot = {
            "progress": dict(_fetch_state.get("progress") or {}),
            "activity": dict(_fetch_state.get("activity") or {}),
            "activity_log": list(_fetch_state.get("activity_log") or []),
            "log": list(_fetch_state.get("log") or []),
            "review_jobs": _fetch_state.get("review_jobs"),
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
        review_jobs=snapshot["review_jobs"],
        cancel_requested=snapshot["cancel_requested"],
        new_jobs=snapshot["new_jobs"],
        result_line=snapshot["result_line"],
    )


def persist_fetch_run(run_id: int | None = None) -> None:
    with _fetch_lock:
        rid = run_id or _fetch_state.get("run_id")
        if not rid:
            return
        payload = {
            "finished_at": _fetch_state.get("finished_at") or utc_now(),
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
            "review_jobs": _fetch_state.get("review_jobs"),
        }
    row = fetch_repo.finalize_fetch_run(int(rid), **payload)
    with _fetch_lock:
        _fetch_state["last_fetch_run"] = row
        _fetch_state["run_id"] = None


def reap_zombie_fetch() -> None:
    should_finalize = False
    with _fetch_lock:
        if _fetch_state.get("running"):
            thread = _fetch_thread
            if thread is None:
                return
            if thread.is_alive():
                return
            _fetch_state["running"] = False
            if _fetch_state.get("exit_code") is None:
                _fetch_state["exit_code"] = 1
                _fetch_state["log"].append("Fetch thread stopped unexpectedly")
            if not _fetch_state.get("finished_at"):
                _fetch_state["finished_at"] = utc_now()
            should_finalize = bool(_fetch_state.get("run_id"))
    if should_finalize:
        persist_fetch_run()
    with _fetch_lock:
        local_running = bool(_fetch_state.get("running"))
    if not local_running:
        fetch_repo.reap_orphan_running_fetch_runs()


def build_fetch_status() -> dict:
    reap_zombie_fetch()
    with _fetch_lock:
        if _fetch_state.get("running"):
            return memory_status()
        if _fetch_state.get("last_fetch_run") is not None:
            return memory_status()
    row = fetch_repo.get_running_fetch_run()
    if row:
        return status_from_row(row)
    return idle_fetch_status()


def fetch_is_running() -> bool:
    reap_zombie_fetch()
    with _fetch_lock:
        if _fetch_state.get("running"):
            return True
    return fetch_repo.get_running_fetch_run() is not None


def guard_fetch_start() -> bool:
    reap_zombie_fetch()
    with _fetch_lock:
        if _fetch_state.get("running"):
            return False
    return fetch_repo.get_running_fetch_run() is None


def wait_for_fetch_thread(timeout: float | None = None) -> bool:
    with _fetch_lock:
        thread = _fetch_thread
    if thread is None:
        return True
    thread.join(timeout=timeout)
    return not thread.is_alive()


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
    sync_live_to_db()
    return True, None


def reset_for_run(
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
    started_at = utc_now()
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
        "progress": {"current": 0, "total": 0, "company": None, "status": "", "company_results": []},
        "activity": {"message": "", "detail": ""},
        "activity_log": [],
        "log": [],
        "review_jobs": None,
        "new_jobs_total": 0,
        "last_fetch_run": None,
    })
    sync_live_to_db()
    return run_id


def set_fetch_thread(thread: threading.Thread | None) -> None:
    global _fetch_thread
    _fetch_thread = thread


def update_progress(progress: dict) -> None:
    with _fetch_lock:
        prev = dict(_fetch_state.get("progress") or {})
        company_results = prev.get("company_results") or progress.get("company_results") or []
        merged = dict(progress)
        if company_results:
            merged["company_results"] = list(company_results)
        _fetch_state["progress"] = merged
    sync_live_to_db()


def record_company_result(company_name: str, new_count: int, jobs: list[dict]) -> None:
    if new_count <= 0:
        return
    with _fetch_lock:
        _fetch_state["new_jobs_total"] = int(_fetch_state.get("new_jobs_total") or 0) + int(new_count)
        progress = dict(_fetch_state.get("progress") or {})
        results = list(progress.get("company_results") or [])
        results.append({
            "company": company_name,
            "new_count": int(new_count),
            "jobs": list(jobs or []),
        })
        progress["company_results"] = results
        _fetch_state["progress"] = progress
    sync_live_to_db()


def append_log_line(line: str) -> None:
    with _fetch_lock:
        _fetch_state["log"].append(line)


def set_review_jobs(payload: dict) -> None:
    with _fetch_lock:
        _fetch_state["review_jobs"] = payload
    sync_live_to_db()


def mutate_state(mutator) -> None:
    with _fetch_lock:
        mutator(_fetch_state)


def fetch_lock():
    return _fetch_lock


def reset_for_tests() -> None:
    global _fetch_thread
    with _fetch_lock:
        _fetch_state.clear()
        _fetch_state.update(idle_fetch_status())
        _fetch_thread = None
