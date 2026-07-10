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
