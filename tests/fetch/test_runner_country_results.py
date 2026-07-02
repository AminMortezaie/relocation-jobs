from __future__ import annotations

from relocation_jobs.fetch import runner as fetch_runner


def test_on_company_result_updates_live_new_jobs_and_progress():
    with fetch_runner._fetch_lock:
        fetch_runner._fetch_state.clear()
        fetch_runner._fetch_state.update({
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
        })

    fetch_runner._on_company_result(
        "Acme",
        2,
        [
            {"title": "Backend Engineer", "url": "https://example.com/jobs/1"},
            {"title": "Platform Engineer", "url": "https://example.com/jobs/2"},
        ],
    )

    with fetch_runner._fetch_lock:
        assert fetch_runner._fetch_state["new_jobs_total"] == 2
        results = fetch_runner._fetch_state["progress"]["company_results"]
        assert len(results) == 1
        assert results[0]["company"] == "Acme"
        assert results[0]["new_count"] == 2
        assert len(results[0]["jobs"]) == 2


def test_on_country_progress_preserves_company_results():
    with fetch_runner._fetch_lock:
        fetch_runner._fetch_state.clear()
        fetch_runner._fetch_state.update({
            "progress": {
                "current": 1,
                "total": 3,
                "company": "Acme",
                "status": "done",
                "company_results": [
                    {"company": "Acme", "new_count": 1, "jobs": [{"title": "Role", "url": "https://x"}]},
                ],
            },
        })

    fetch_runner._on_country_progress({
        "current": 2,
        "total": 3,
        "company": "Beta",
        "status": "fetching",
    })

    with fetch_runner._fetch_lock:
        progress = fetch_runner._fetch_state["progress"]
        assert progress["current"] == 2
        assert progress["company"] == "Beta"
        assert len(progress["company_results"]) == 1
        assert progress["company_results"][0]["company"] == "Acme"
