from __future__ import annotations

from relocation_jobs.fetch import state as fetch_state


def test_on_company_result_updates_live_new_jobs_and_progress():
    fetch_state.reset_for_tests()
    with fetch_state.fetch_lock():
        fetch_state.mutate_state(lambda st: st.update({
            "running": True,
            "run_id": None,
            "new_jobs_total": 0,
            "progress": {
                "current": 1,
                "total": 3,
                "company": "Acme",
                "status": "done",
                "company_results": [],
            },
        }))

    fetch_state.record_company_result(
        "Acme",
        2,
        [
            {"title": "Backend Engineer", "url": "https://example.com/jobs/1"},
            {"title": "Platform Engineer", "url": "https://example.com/jobs/2"},
        ],
    )

    with fetch_state.fetch_lock():
        status = fetch_state.memory_status()
        assert status["new_jobs_total"] == 2
        results = status["progress"]["company_results"]
        assert len(results) == 1
        assert results[0]["company"] == "Acme"
        assert results[0]["new_count"] == 2
        assert len(results[0]["jobs"]) == 2


def test_on_country_progress_preserves_company_results():
    fetch_state.reset_for_tests()
    with fetch_state.fetch_lock():
        fetch_state.mutate_state(lambda st: st.update({
            "running": True,
            "progress": {
                "current": 1,
                "total": 3,
                "company": "Acme",
                "status": "done",
                "company_results": [
                    {"company": "Acme", "new_count": 1, "jobs": [{"title": "Role", "url": "https://x"}]},
                ],
            },
        }))

    fetch_state.update_progress({
        "current": 2,
        "total": 3,
        "company": "Beta",
        "status": "fetching",
    })

    with fetch_state.fetch_lock():
        progress = fetch_state.memory_status()["progress"]
        assert progress["current"] == 2
        assert progress["company"] == "Beta"
        assert len(progress["company_results"]) == 1
        assert progress["company_results"][0]["company"] == "Acme"
