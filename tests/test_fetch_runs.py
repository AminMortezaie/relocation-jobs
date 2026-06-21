"""Fetch run persistence in panel DB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from relocation_jobs.db import init_db, list_fetch_runs, record_fetch_run


@pytest.mark.integration
def test_record_and_list_fetch_runs(test_user):
    user_id = test_user["id"]
    started = datetime.now(timezone.utc).replace(microsecond=0)
    finished = started + timedelta(seconds=95)

    row = record_fetch_run(
        user_id=user_id,
        country="uk",
        company_name=None,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        exit_code=0,
        cancelled=False,
        new_jobs=4,
        concurrency=8,
        companies_done=12,
        companies_total=12,
        result_line="Done 12 companies",
    )
    assert row["id"]
    assert row["scope"] == "country"
    assert row["new_jobs"] == 4
    assert row["duration_seconds"] == pytest.approx(95.0)

    company_row = record_fetch_run(
        user_id=user_id,
        country="germany",
        company_name="Acme GmbH",
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        exit_code=0,
        new_jobs=1,
        concurrency=1,
        companies_done=1,
        companies_total=1,
    )
    assert company_row["scope"] == "company"
    assert company_row["company_name"] == "Acme GmbH"

    uk_runs = list_fetch_runs(user_id, country="uk", limit=10)
    assert len(uk_runs) == 1
    assert uk_runs[0]["country"] == "uk"

    all_runs = list_fetch_runs(user_id, limit=10)
    assert len(all_runs) >= 2
    assert all_runs[0]["country"] in {"uk", "germany"}


@pytest.mark.integration
def test_fetch_runs_table_created_on_init(db):
    del db
    init_db()
    from relocation_jobs.db import get_connection

    conn = get_connection()
    if hasattr(conn, "execute"):
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fetch_runs'"
        ).fetchall()
        assert rows
