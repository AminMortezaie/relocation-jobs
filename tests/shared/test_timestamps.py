from __future__ import annotations

from relocation_jobs.shared.timestamps import (
    company_activity_ts,
    company_newest_job_fetched,
    job_fetched_ts,
)


def test_company_activity_ts_uses_max_job_fetched_not_company_updated():
    company = {
        "updated": "2026-06-28T10:00:00+00:00",
        "added": "2025-01-01",
    }
    jobs = [
        {"fetched": "2026-06-24T22:49:00+00:00"},
        {"fetched": "2026-06-20T12:00:00+00:00"},
    ]
    assert company_activity_ts(company, jobs) == "2026-06-24T22:49:00+00:00"


def test_company_activity_ts_scout24_beats_older_flixbus_style_ordering():
    flixbus = {
        "updated": "2026-06-28T10:00:00+00:00",
        "added": "2025-01-01",
    }
    scout24 = {
        "updated": "2026-06-24T10:00:00+00:00",
        "added": "2025-01-01",
    }
    flix_ts = company_activity_ts(
        flixbus,
        [{"fetched": "2026-06-24T22:49:00+00:00"}],
    )
    scout_ts = company_activity_ts(
        scout24,
        [{"fetched": "2026-06-25T00:45:00+00:00"}],
    )
    assert scout_ts > flix_ts


def test_job_fetched_ts_ignores_last_seen():
    assert job_fetched_ts({"fetched": "", "last_seen": "2026-06-25T00:45:00+00:00"}) == ""


def test_company_newest_job_fetched_ignores_not_for_me_bucket():
    company = {"added": "2025-01-01"}
    board_jobs = [{"fetched": "2026-06-24T22:49:00+00:00"}]
    # not-for-me roles are not passed in board_jobs
    assert company_newest_job_fetched(board_jobs, company) == "2026-06-24T22:49:00+00:00"
    assert company_newest_job_fetched([], company) == "2025-01-01"
