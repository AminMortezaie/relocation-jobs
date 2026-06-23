#!/usr/bin/env python3
"""
Job opportunities dashboard — view cached matches and trigger new scrapes.

    python3 scripts/panel_server.py
    # or: python3 -m relocation_jobs.panel_server
    # open http://127.0.0.1:5050
"""

from __future__ import annotations

import os
import subprocess

from relocation_jobs.catalog_db import touch_country_meta
from relocation_jobs.web import deps, fetch_state
from relocation_jobs.web.app import ROOT, STATIC, _bootstrapped, app, bootstrap_app
from relocation_jobs.web.helpers import scrape_enabled
from relocation_jobs.web.scrape_runner import (
    _LogWriter,
    _activity_from_scrape_line,
    _build_fetch_run_snapshot,
    _build_scrape_cmd,
    _handle_scrape_ipc_line,
    _log,
    _on_scrape_progress,
    _on_scrape_review,
    _persist_fetch_run,
    _push_fetch_activity,
    _reap_zombie_fetch,
    _reset_fetch_run_state,
    _run_scrape,
    _should_cancel_fetch,
    _start_scrape_thread,
    _sync_fetch_run,
    _terminate_scrape_process,
    build_fetch_status_payload,
    fetch_is_running,
)

# Re-export for tests that monkeypatch relocation_jobs.panel_server.*
HTTPX_AVAILABLE = deps.HTTPX_AVAILABLE
DEFAULT_CONCURRENCY = deps.DEFAULT_CONCURRENCY
add_company = deps.add_company
set_job_applied = deps.set_job_applied
set_job_rejected = deps.set_job_rejected
set_job_reapply = deps.set_job_reapply
set_job_ats_score = deps.set_job_ats_score
set_job_waiting_referral = deps.set_job_waiting_referral
set_job_not_for_me = deps.set_job_not_for_me
set_job_looking_to_apply = deps.set_job_looking_to_apply
set_job_seen = deps.set_job_seen
set_company_applied = deps.set_company_applied
set_company_awaiting_response = deps.set_company_awaiting_response

_fetch_lock = fetch_state._fetch_lock
_fetch_state = fetch_state._fetch_state


def __getattr__(name: str):
    if name == "_fetch_thread":
        return fetch_state._fetch_thread
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main():
    port = int(os.environ.get("PORT", "5050"))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    print(f"Job panel: http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
