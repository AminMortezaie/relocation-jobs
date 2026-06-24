from __future__ import annotations

import pytest
import respx
from httpx import Response

from relocation_jobs.v2.scrape.boards.greenhouse import greenhouse_jobs_api_url


def test_jobs_stats_recent_fetch_runs(v2_auth_client, seeded_catalog_v2, db):
    from relocation_jobs.db import get_user_by_username
    from relocation_jobs.v2.fetch import repo as fetch_repo

    del db
    user_id = get_user_by_username("admin")["id"]
    started = "2025-06-01T12:00:00+00:00"
    finished = "2025-06-01T12:05:00+00:00"
    run_id = fetch_repo.create_fetch_run(
        user_id=user_id,
        country="uk",
        company_name=None,
        file_name="uk.json",
        concurrency=1,
        started_at=started,
    )["id"]
    fetch_repo.finalize_fetch_run(
        int(run_id),
        finished_at=finished,
        exit_code=0,
        new_jobs=3,
        companies_done=1,
        companies_total=1,
        result_line="Done",
    )

    stats = v2_auth_client.get("/api/jobs?country=uk").get_json()["stats"]
    assert len(stats["recent_fetch_runs"]) == 1
    assert stats["recent_fetch_runs"][0]["country"] == "uk"
    assert stats["recent_fetch_runs"][0]["new_jobs"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_run_single_company_fetch_greenhouse(seeded_catalog_v2):
    respx.get(greenhouse_jobs_api_url("acmebackend")).mock(
        return_value=Response(
            200,
            json={
                    "jobs": [
                        {
                            "title": "Senior Backend Engineer",
                            "absolute_url": "https://boards.greenhouse.io/acmebackend/jobs/424242",
                        },
                    ],
            },
        ),
    )
    from relocation_jobs.v2.catalog.repo import get_company
    from relocation_jobs.v2.fetch.runner import run_single_company_fetch_async

    msg, new_count = await run_single_company_fetch_async("uk", "Acme Backend Ltd")
    assert new_count == 1
    assert "1 new" in msg

    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    urls = {j["url"] for j in company["matching_jobs"]}
    assert "https://boards.greenhouse.io/acmebackend/jobs/424242" in urls


@pytest.mark.asyncio
@respx.mock
async def test_country_fetch_runner(seeded_catalog_v2, db):
    from relocation_jobs.db import get_user_by_username
    from relocation_jobs.v2.catalog.repo import get_company
    from relocation_jobs.v2.fetch import repo as fetch_repo
    from relocation_jobs.v2.fetch.country_runner import run_country_fetch

    del db
    user_id = get_user_by_username("admin")["id"]
    respx.get(greenhouse_jobs_api_url("acmebackend")).mock(
        return_value=Response(
            200,
            json={
                "jobs": [
                    {
                        "title": "Senior Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acmebackend/jobs/999",
                    },
                ],
            },
        ),
    )
    run_id = int(fetch_repo.create_fetch_run(
        user_id=user_id,
        country="uk",
        company_name=None,
        file_name="uk.json",
        concurrency=1,
        started_at="2025-06-01T10:00:00+00:00",
    )["id"])

    import httpx

    async with httpx.AsyncClient() as client:
        new_jobs, done, cancelled = await run_country_fetch(
            client,
            "uk",
            run_id=run_id,
        )

    assert cancelled is False
    assert done == 1
    assert new_jobs == 1
    company = get_company("uk", "Acme Backend Ltd")
    assert any("jobs/999" in j["url"] for j in company["matching_jobs"])


def test_companies_fetch_api(v2_auth_client, seeded_catalog_v2, monkeypatch):
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    started: list[tuple[str, str, int]] = []

    def fake_start(*, user_id, country_key, company_name):
        started.append((country_key, company_name, user_id))
        return 42

    monkeypatch.setattr(
        "relocation_jobs.v2.web.routes.companies.start_company_fetch",
        fake_start,
    )

    resp = v2_auth_client.post(
        "/api/companies/fetch",
        json={"country": "uk", "company": "Acme Backend Ltd"},
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["run_id"] == 42
    assert payload["company"] == "Acme Backend Ltd"
    assert len(started) == 1
    assert started[0][0] == "uk"
    assert started[0][1] == "Acme Backend Ltd"


def test_company_fetch_worker_integration(seeded_catalog_v2, db, monkeypatch):
    from relocation_jobs.db import get_user_by_username
    from relocation_jobs.v2.catalog.repo import get_company
    from relocation_jobs.v2.fetch import repo as fetch_repo
    from relocation_jobs.v2.fetch.runner import _company_fetch_worker

    del db

    async def noop_enrich(_client, jobs, _company, **kwargs):
        return jobs

    monkeypatch.setattr(
        "relocation_jobs.v2.fetch.pipeline.enrich_jobs",
        noop_enrich,
    )

    user_id = get_user_by_username("admin")["id"]
    with respx.mock:
        respx.get(greenhouse_jobs_api_url("acmebackend")).mock(
            return_value=Response(
                200,
                json={
                    "jobs": [
                        {
                            "title": "Senior Backend Engineer",
                            "absolute_url": "https://boards.greenhouse.io/acmebackend/jobs/888",
                        },
                    ],
                },
            ),
        )
        run_id = int(fetch_repo.create_fetch_run(
            user_id=user_id,
            country="uk",
            company_name="Acme Backend Ltd",
            file_name="uk.json",
            concurrency=1,
            started_at="2025-06-01T10:00:00+00:00",
        )["id"])
        _company_fetch_worker("uk", "Acme Backend Ltd", run_id=run_id)

    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    assert any("jobs/888" in j["url"] for j in company["matching_jobs"])
    row = fetch_repo.list_user_fetch_runs(user_id, country="uk", limit=5)
    finished = [r for r in row if int(r["id"]) == run_id]
    assert finished
    assert finished[0]["exit_code"] == 0
    assert finished[0]["new_jobs"] == 1


def test_companies_fetch_409_when_busy(v2_auth_client, seeded_catalog_v2, monkeypatch):
    from relocation_jobs.db import get_user_by_username
    from relocation_jobs.v2.fetch import repo as fetch_repo

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    user_id = get_user_by_username("admin")["id"]
    fetch_repo.create_fetch_run(
        user_id=user_id,
        country="uk",
        company_name=None,
        file_name="uk.json",
        concurrency=1,
        started_at="2025-06-01T12:00:00+00:00",
    )

    resp = v2_auth_client.post(
        "/api/companies/fetch",
        json={"country": "uk", "company": "Acme Backend Ltd"},
    )
    assert resp.status_code == 409
    assert "already running" in resp.get_json()["error"].lower()


def test_country_fetch_disabled(v2_auth_client, monkeypatch):
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "0")
    resp = v2_auth_client.post("/api/fetch", json={"country": "uk"})
    assert resp.status_code == 503
