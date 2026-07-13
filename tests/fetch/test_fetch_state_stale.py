from __future__ import annotations

from unittest.mock import MagicMock, patch

from relocation_jobs.fetch import state as fetch_state


def test_persist_fetch_run_skips_already_finalized_run(db, monkeypatch):
    del db
    fetch_state.reset_for_tests()
    fetch_state.mutate_state(lambda st: st.update({
        "running": True,
        "run_id": 99,
        "exit_code": 0,
        "finished_at": fetch_state.utc_now(),
    }))
    monkeypatch.setattr(
        "relocation_jobs.fetch.state.fetch_repo.fetch_run_is_running",
        lambda run_id: False,
    )
    finalize = MagicMock(return_value={"id": 99})
    monkeypatch.setattr("relocation_jobs.fetch.state.fetch_repo.finalize_fetch_run", finalize)

    fetch_state.persist_fetch_run(99)

    finalize.assert_not_called()


def test_reset_for_run_clears_previous_review_jobs(db, monkeypatch):
    """Running status after reset must not expose the previous run's review_jobs."""
    del db
    fetch_state.reset_for_tests()
    fetch_state.mutate_state(lambda st: st.update({
        "running": False,
        "review_jobs": {
            "included": [{"title": "Old", "url": "https://example.com/old"}],
            "filtered": [],
        },
        "company": "Acme",
        "country": "nl",
    }))
    monkeypatch.setattr(
        "relocation_jobs.fetch.state.fetch_repo.create_fetch_run",
        lambda **kwargs: {"id": 42},
    )
    monkeypatch.setattr("relocation_jobs.fetch.state.sync_live_to_db", lambda: None)

    run_id = fetch_state.reset_for_run(
        user_id=1,
        country="nl",
        file_name="nl.json",
        concurrency=1,
        company="Swisslog",
    )

    status = fetch_state.memory_status()
    assert run_id == 42
    assert status["running"] is True
    assert status["company"] == "Swisslog"
    assert status["review_jobs"] is None
    assert status["log"] == []
    assert status["last_fetch_run"] is None


def test_mutate_state_for_run_ignores_stale_run_id(db):
    del db
    fetch_state.reset_for_tests()
    fetch_state.mutate_state(lambda st: st.update({
        "running": True,
        "run_id": 2,
    }))
    touched: list[int] = []

    def mutator(st: dict) -> None:
        touched.append(int(st.get("run_id") or 0))
        st["result_line"] = "stale"

    fetch_state.mutate_state_for_run(1, mutator)

    assert touched == []
    assert fetch_state.memory_status()["result_line"] is None


def test_update_progress_for_run_ignores_stale_run_id(db):
    del db
    fetch_state.reset_for_tests()
    fetch_state.mutate_state(lambda st: st.update({
        "running": True,
        "run_id": 5,
        "progress": {"current": 0, "total": 10},
    }))

    fetch_state.update_progress_for_run(4, {"current": 9, "total": 10})

    assert fetch_state.memory_status()["progress"]["current"] == 0
