"""Flask panel API — auth, config, jobs listing with tracking overlay."""

import pytest


@pytest.mark.integration
def test_auth_login_and_status(app_client):
    status = app_client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.get_json()["authenticated"] is False

    bad = app_client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    ok = app_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass123"},
    )
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == "admin"


@pytest.mark.integration
def test_protected_routes_require_auth(app_client):
    assert app_client.get("/api/jobs").status_code == 401
    assert app_client.get("/api/countries").status_code == 401


@pytest.mark.integration
def test_jobs_listing_with_catalog(auth_client, seeded_catalog, test_user):
    resp = auth_client.get("/api/jobs?country=uk")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "companies" in body
    assert len(body["companies"]) >= 1
    company = body["companies"][0]
    assert company["name"] == "Acme Backend Ltd"
    assert len(company["jobs"]) == 2


@pytest.mark.integration
def test_job_applied_api(auth_client, seeded_catalog, test_user):
    jobs_resp = auth_client.get("/api/jobs?country=uk")
    job = jobs_resp.get_json()["companies"][0]["jobs"][0]

    applied = auth_client.post(
        "/api/jobs/applied",
        json={
            "country": "uk",
            "company": job["company"],
            "url": job["url"],
            "applied": True,
        },
    )
    assert applied.status_code == 200
    assert applied.get_json()["applied"] is True

    jobs_resp = auth_client.get("/api/jobs?country=uk")
    updated = next(
        j for j in jobs_resp.get_json()["companies"][0]["jobs"] if j["url"] == job["url"]
    )
    assert updated["applied"] is True


@pytest.mark.integration
def test_config_reports_scrape_disabled(auth_client, monkeypatch):
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "0")
    resp = auth_client.get("/api/config")
    assert resp.status_code == 200
    assert resp.get_json()["scrape_enabled"] is False
