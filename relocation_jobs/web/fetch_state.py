"""In-memory scrape fetch run state (shared by scrape_runner and tests)."""

from __future__ import annotations

import threading
from collections import deque

from relocation_jobs.core.ats_constants import DEFAULT_CONCURRENCY

_fetch_lock = threading.RLock()
_fetch_state: dict = {
    "running": False,
    "country": None,
    "company": None,
    "ats_type": None,
    "file": None,
    "concurrency": DEFAULT_CONCURRENCY,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "result_line": None,
    "cancel_requested": False,
    "cancelled": False,
    "progress": {"current": 0, "total": 0, "company": None, "status": ""},
    "review_jobs": None,
    "activity": {"message": "", "detail": ""},
    "activity_log": deque(maxlen=20),
    "activity_touch_company": None,
    "new_jobs_total": 0,
    "log": deque(maxlen=200),
    "process": None,
    "user_id": None,
    "fetch_run_recorded": False,
    "last_fetch_run": None,
}

_fetch_thread: threading.Thread | None = None
