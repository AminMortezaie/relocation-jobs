from __future__ import annotations

from relocation_jobs.fetch import state as fetch_state


def test_reap_zombie_skips_orphan_reap_when_panel_scrape_disabled(monkeypatch):
    fetch_state.reset_for_tests()
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "0")
    reaped: list[int] = []

    monkeypatch.setattr(
        "relocation_jobs.fetch.state.fetch_repo.reap_orphan_running_fetch_runs",
        lambda **kwargs: reaped.append(1) or 0,
    )

    fetch_state.reap_zombie_fetch()

    assert reaped == []


def test_reap_zombie_reaps_orphans_when_panel_scrape_enabled(monkeypatch):
    fetch_state.reset_for_tests()
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    reaped: list[int] = []

    monkeypatch.setattr(
        "relocation_jobs.fetch.state.fetch_repo.reap_orphan_running_fetch_runs",
        lambda **kwargs: reaped.append(1) or 2,
    )

    fetch_state.reap_zombie_fetch()

    assert reaped == [1]
