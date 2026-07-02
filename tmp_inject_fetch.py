
import time
from relocation_jobs.fetch import runner as fetch_runner

with fetch_runner._fetch_lock:
    fetch_runner._fetch_state.clear()
    fetch_runner._fetch_state.update({
        "running": True,
        "run_id": None,
        "country": "netherlands",
        "company": None,
        "ats_type": None,
        "file": None,
        "started_at": "2026-07-01T12:00:00+00:00",
        "finished_at": None,
        "exit_code": None,
        "concurrency": 1,
        "result_line": None,
        "cancel_requested": False,
        "cancelled": False,
        "progress": {
            "current": 0,
            "total": 3,
            "company": None,
            "status": "starting",
            "company_results": [],
        },
        "activity": {"message": "Starting", "detail": ""},
        "activity_log": [],
        "log": ["Starting…"],
        "review_jobs": None,
        "new_jobs_total": 0,
        "last_fetch_run": None,
    })

time.sleep(2)
fetch_runner._on_company_result(
    "Acme Corp",
    2,
    [
        {"title": "Backend Engineer", "url": "https://example.com/jobs/backend"},
        {"title": "Platform Engineer", "url": "https://example.com/jobs/platform"},
    ],
)
time.sleep(2)
fetch_runner._on_country_progress({
    "current": 1,
    "total": 3,
    "company": "Beta GmbH",
    "status": "fetching",
})
time.sleep(1)
fetch_runner._on_company_result(
    "Beta GmbH",
    1,
    [{"title": "Data Engineer", "url": "https://example.com/jobs/data"}],
)
time.sleep(2)
with fetch_runner._fetch_lock:
    fetch_runner._fetch_state["running"] = False
    fetch_runner._fetch_state["finished_at"] = "2026-07-01T12:05:00+00:00"
    fetch_runner._fetch_state["exit_code"] = 0
    fetch_runner._fetch_state["result_line"] = "Done 3 companies, 3 new jobs"
    prog = dict(fetch_runner._fetch_state.get("progress") or {})
    prog.update({"current": 3, "total": 3, "company": None, "status": "done"})
    fetch_runner._fetch_state["progress"] = prog
