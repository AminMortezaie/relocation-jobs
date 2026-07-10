from __future__ import annotations

import pytest

from relocation_jobs.fetch.scheduler import (
    run_fetch_cycle,
    schedule_concurrency,
    schedule_countries,
    schedule_enabled,
)


def test_schedule_enabled_reads_env(monkeypatch):
    monkeypatch.delenv("FETCH_SCHEDULE_ENABLED", raising=False)
    assert schedule_enabled() is False
    monkeypatch.setenv("FETCH_SCHEDULE_ENABLED", "1")
    assert schedule_enabled() is True


def test_schedule_countries_defaults_to_supported(monkeypatch):
    monkeypatch.delenv("FETCH_SCHEDULE_COUNTRIES", raising=False)
    countries = schedule_countries()
    assert "uk" in countries
    assert "netherlands" in countries


def test_schedule_countries_override(monkeypatch):
    monkeypatch.setenv("FETCH_SCHEDULE_COUNTRIES", "uk,netherlands")
    assert schedule_countries() == ("uk", "netherlands")


def test_schedule_concurrency_caps_at_max(monkeypatch):
    monkeypatch.setenv("FETCH_SCHEDULE_CONCURRENCY", "99")
    from relocation_jobs.core.ats_constants import MAX_CONCURRENCY

    assert schedule_concurrency() == MAX_CONCURRENCY


def test_run_fetch_cycle_skips_when_busy(db, monkeypatch):
    from relocation_jobs.users.repo import resolve_scheduler_user_id

    del db
    monkeypatch.setenv("FETCH_SCHEDULE_ENABLED", "1")
    monkeypatch.setattr(
        "relocation_jobs.fetch.state.fetch_is_running",
        lambda: True,
    )
    user_id = resolve_scheduler_user_id()

    result = run_fetch_cycle(user_id=user_id)

    assert result["skipped"] is True
    assert result["reason"] == "fetch_busy"


def test_run_fetch_cycle_starts_configured_countries(db, monkeypatch):
    from relocation_jobs.users.repo import resolve_scheduler_user_id

    del db
    monkeypatch.setenv("FETCH_SCHEDULE_ENABLED", "1")
    monkeypatch.setenv("FETCH_SCHEDULE_COUNTRIES", "uk,netherlands")
    monkeypatch.setenv("FETCH_SCHEDULE_CONCURRENCY", "2")

    started: list[tuple[int, str, int]] = []

    def fake_start_country_fetch(**kwargs):
        started.append((kwargs["user_id"], kwargs["country_key"], kwargs["concurrency"]))
        return len(started)

    monkeypatch.setattr(
        "relocation_jobs.fetch.scheduler.start_country_fetch",
        fake_start_country_fetch,
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.state.wait_for_fetch_thread",
        lambda timeout=None: True,
    )

    user_id = resolve_scheduler_user_id()
    result = run_fetch_cycle(user_id=user_id)

    assert result["skipped"] is False
    assert result["started"] == ["uk", "netherlands"]
    assert started == [
        (user_id, "uk", 2),
        (user_id, "netherlands", 2),
    ]


def test_run_fetch_cycle_abandons_on_country_timeout(db, monkeypatch):
    from relocation_jobs.users.repo import resolve_scheduler_user_id

    del db
    monkeypatch.setenv("FETCH_SCHEDULE_ENABLED", "1")
    monkeypatch.setenv("FETCH_SCHEDULE_COUNTRIES", "uk")

    abandoned: list[dict] = []

    def fake_abandon(*, result_line: str) -> None:
        abandoned.append({"result_line": result_line})

    monkeypatch.setattr(
        "relocation_jobs.fetch.scheduler.start_country_fetch",
        lambda **kwargs: 42,
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.state.wait_for_fetch_thread",
        lambda timeout=None: False,
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.state.abandon_fetch_after_timeout",
        fake_abandon,
    )

    user_id = resolve_scheduler_user_id()
    result = run_fetch_cycle(user_id=user_id)

    assert result["skipped"] is False
    assert result["started"] == ["uk"]
    assert len(abandoned) == 1
    assert "timed out" in abandoned[0]["result_line"]


def test_run_fetch_cycle_disabled(monkeypatch):
    monkeypatch.setenv("FETCH_SCHEDULE_ENABLED", "0")
    result = run_fetch_cycle(user_id=1)
    assert result["skipped"] is True
    assert result["reason"] == "schedule_disabled"


def test_resolve_scheduler_user_id(db):
    from relocation_jobs.users.repo import resolve_scheduler_user_id

    del db
    user_id = resolve_scheduler_user_id()
    assert user_id > 0


def test_resolve_scheduler_user_id_missing_user(monkeypatch):
    from relocation_jobs.users.repo import resolve_scheduler_user_id

    monkeypatch.setenv("PANEL_ADMIN_USER", "no-such-admin")
    with pytest.raises(LookupError, match="no-such-admin"):
        resolve_scheduler_user_id()
