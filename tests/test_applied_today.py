"""Applied-today stat: count only real apply events, not tracking touch-ups."""

from __future__ import annotations

import pytest

from relocation_jobs.db import (
    count_jobs_applied_today_db,
    db_transaction,
    list_jobs_applied_today_db,
    set_job_applied_db,
    set_job_seen_db,
    use_postgres,
)
from relocation_jobs.panel_data import compute_stats


@pytest.fixture
def fixed_day_bounds(monkeypatch):
    """Pin 'today' to 2026-06-21 UTC for deterministic bounds."""
    start = "2026-06-21T00:00:00+00:00"
    end = "2026-06-22T00:00:00+00:00"
    monkeypatch.setattr("relocation_jobs.db._local_day_utc_bounds", lambda tz: (start, end))
    return start, end


def _insert_apply_event(
    user_id: int,
    country: str,
    company: str,
    url: str,
    *,
    created_at: str,
    event_date: str,
    job_title: str = "Engineer",
) -> None:
    ph = "%s" if use_postgres() else "?"
    with db_transaction() as conn:
        conn.execute(
            f"""
            INSERT INTO job_tracking (
                user_id, country, company_name, job_url, job_title,
                applied, applied_date, not_for_me, not_for_me_date,
                looking_to_apply, looking_to_apply_date, updated_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, 1, {ph}, 0, NULL, 0, NULL, {ph})
            ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                applied = 1,
                applied_date = excluded.applied_date,
                job_title = excluded.job_title,
                updated_at = excluded.updated_at
            """,
            (user_id, country, company, url, job_title, event_date, created_at),
        )
        conn.execute(
            f"""
            INSERT INTO job_status_events (
                user_id, country, company_name, job_url,
                event_type, event_date, created_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, 'applied', {ph}, {ph})
            """,
            (user_id, country, company, url, event_date, created_at),
        )


@pytest.mark.integration
def test_apply_event_today_counts(test_user, fixed_day_bounds):
    uid = test_user["id"]
    url = "https://example.com/jobs/today-apply"
    _insert_apply_event(
        uid,
        "uk",
        "Today Co",
        url,
        created_at="2026-06-21T10:00:00+00:00",
        event_date="2026-06-21",
        job_title="Backend Engineer",
    )

    assert count_jobs_applied_today_db(uid, timezone_name="UTC") == 1
    jobs = list_jobs_applied_today_db(uid, timezone_name="UTC")
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Today Co"
    assert jobs[0]["title"] == "Backend Engineer"
    assert jobs[0]["url"] == url


@pytest.mark.integration
def test_old_apply_with_tracking_touch_today_not_counted(test_user, fixed_day_bounds):
    """Regression: updated_at bumps must not inflate applied today."""
    uid = test_user["id"]
    url = "https://example.com/jobs/old-apply"
    _insert_apply_event(
        uid,
        "germany",
        "Trivago",
        url,
        created_at="2026-06-08T12:00:00+00:00",
        event_date="2026-06-08",
    )

    set_job_seen_db(uid, "germany", "Trivago", url, True)

    assert count_jobs_applied_today_db(uid, timezone_name="Asia/Yerevan") == 0
    assert list_jobs_applied_today_db(uid, country="germany", timezone_name="Asia/Yerevan") == []


@pytest.mark.integration
def test_country_filter_limits_applied_today(test_user, fixed_day_bounds):
    uid = test_user["id"]
    _insert_apply_event(
        uid,
        "germany",
        "Berlin Co",
        "https://example.com/jobs/de",
        created_at="2026-06-21T09:00:00+00:00",
        event_date="2026-06-21",
    )
    _insert_apply_event(
        uid,
        "uk",
        "London Co",
        "https://example.com/jobs/uk",
        created_at="2026-06-21T11:00:00+00:00",
        event_date="2026-06-21",
    )

    assert count_jobs_applied_today_db(uid, country="germany", timezone_name="UTC") == 1
    assert count_jobs_applied_today_db(uid, country="uk", timezone_name="UTC") == 1
    assert count_jobs_applied_today_db(uid, timezone_name="UTC") == 2


@pytest.mark.integration
def test_duplicate_apply_events_same_day_count_once(test_user, fixed_day_bounds):
    uid = test_user["id"]
    url = "https://example.com/jobs/dup"
    _insert_apply_event(
        uid,
        "uk",
        "Dup Co",
        url,
        created_at="2026-06-21T08:00:00+00:00",
        event_date="2026-06-21",
    )
    with db_transaction() as conn:
        ph = "%s" if use_postgres() else "?"
        conn.execute(
            f"""
            INSERT INTO job_status_events (
                user_id, country, company_name, job_url,
                event_type, event_date, created_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, 'applied', {ph}, {ph})
            """,
            (uid, "uk", "Dup Co", url, "2026-06-21", "2026-06-21T18:00:00+00:00"),
        )

    assert count_jobs_applied_today_db(uid, timezone_name="UTC") == 1


@pytest.mark.integration
def test_apply_outside_local_day_not_counted(test_user, monkeypatch):
    from zoneinfo import ZoneInfo

    uid = test_user["id"]
    start = "2026-06-21T00:00:00+00:00"
    end = "2026-06-22T00:00:00+00:00"
    monkeypatch.setattr("relocation_jobs.db._local_day_utc_bounds", lambda _tz: (start, end))

    _insert_apply_event(
        uid,
        "uk",
        "Yesterday Co",
        "https://example.com/jobs/yesterday",
        created_at="2026-06-20T22:00:00+00:00",
        event_date="2026-06-20",
    )

    assert count_jobs_applied_today_db(uid, timezone_name="Europe/Berlin") == 0


@pytest.mark.integration
def test_set_job_applied_now_counts_via_event(test_user, fixed_day_bounds):
    uid = test_user["id"]
    url = "https://example.com/jobs/live-apply"
    result = set_job_applied_db(uid, "netherlands", "Live Co", url, True, job_title="Platform Engineer")
    assert result["applied"] is True

    ph = "%s" if use_postgres() else "?"
    with db_transaction() as conn:
        conn.execute(
            f"""
            UPDATE job_status_events
            SET created_at = {ph}, event_date = {ph}
            WHERE user_id = {ph} AND country = {ph} AND company_name = {ph}
              AND job_url = {ph} AND event_type = 'applied'
            """,
            ("2026-06-21T12:30:00+00:00", "2026-06-21", uid, "netherlands", "Live Co", url),
        )

    jobs = list_jobs_applied_today_db(uid, timezone_name="UTC")
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Live Co"


@pytest.mark.integration
def test_compute_stats_includes_applied_today_jobs(test_user, fixed_day_bounds):
    uid = test_user["id"]
    _insert_apply_event(
        uid,
        "uk",
        "Acme Backend Ltd",
        "https://acme.example/jobs/backend-engineer",
        created_at="2026-06-21T15:00:00+00:00",
        event_date="2026-06-21",
        job_title="Backend Engineer",
    )

    stats = compute_stats(
        [],
        [],
        user_id=uid,
        country_key="uk",
        timezone_name="UTC",
    )

    assert stats["positions_applied_today"] == 1
    assert len(stats["applied_today_jobs"]) == 1
    assert stats["applied_today_jobs"][0]["company"] == "Acme Backend Ltd"


@pytest.mark.integration
def test_invalid_timezone_falls_back_to_utc(test_user, fixed_day_bounds):
    uid = test_user["id"]
    _insert_apply_event(
        uid,
        "uk",
        "TZ Co",
        "https://example.com/jobs/tz",
        created_at="2026-06-21T07:00:00+00:00",
        event_date="2026-06-21",
    )
    assert count_jobs_applied_today_db(uid, timezone_name="Invalid/TZ") == 1


@pytest.mark.integration
def test_rows_without_url_are_skipped(test_user, fixed_day_bounds):
    uid = test_user["id"]
    ph = "?" if not use_postgres() else "%s"
    with db_transaction() as conn:
        conn.execute(
            f"""
            INSERT INTO job_status_events (
                user_id, country, company_name, job_url,
                event_type, event_date, created_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, 'applied', {ph}, {ph})
            """,
            (uid, "uk", "Bad Co", "", "2026-06-21", "2026-06-21T10:00:00+00:00"),
        )

    assert count_jobs_applied_today_db(uid, timezone_name="UTC") == 0


@pytest.mark.integration
def test_no_user_returns_zero_applied_today():
    stats = compute_stats([], [])
    assert stats["positions_applied_today"] == 0
    assert stats["applied_today_jobs"] == []
