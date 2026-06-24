from __future__ import annotations


def test_company_detail(v2_auth_client, seeded_catalog_v2):
    resp = v2_auth_client.get("/api/companies/uk/Acme%20Backend%20Ltd")
    assert resp.status_code == 200
    company = resp.get_json()["company"]
    assert company["name"] == "Acme Backend Ltd"
    assert len(company["matching_jobs"]) == 2


def test_fetch_attempts_empty(v2_auth_client, seeded_catalog_v2):
    resp = v2_auth_client.get("/api/fetch/attempts?country=uk")
    assert resp.status_code == 200
    assert resp.get_json()["attempts"] == []


def test_fetch_history(v2_auth_client, seeded_catalog_v2, db):
    from relocation_jobs.db import get_user_by_username
    from relocation_jobs.fetch import repo as fetch_repo

    del db
    user_id = get_user_by_username("admin")["id"]
    run_id = fetch_repo.create_fetch_run(
        user_id=user_id,
        country="uk",
        company_name=None,
        file_name="uk.json",
        concurrency=1,
        started_at="2025-06-01T12:00:00+00:00",
    )["id"]
    fetch_repo.finalize_fetch_run(
        int(run_id),
        finished_at="2025-06-01T12:05:00+00:00",
        exit_code=0,
        new_jobs=2,
    )

    resp = v2_auth_client.get("/api/fetch/history?country=uk&limit=5")
    assert resp.status_code == 200
    runs = resp.get_json()["runs"]
    assert len(runs) == 1
    assert runs[0]["country"] == "uk"
    assert runs[0]["new_jobs"] == 2


def test_admin_dashboard(v2_auth_client, seeded_catalog_v2):
    resp = v2_auth_client.get("/api/admin/dashboard?limit=10")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert "overview" in payload
    assert "catalog" in payload
    assert payload["catalog"]["has_data"] is True
    assert "users" in payload
    assert "runs" in payload
    assert "config" in payload
