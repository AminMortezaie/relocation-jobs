"""Admin API routes and access control."""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

pytestmark = pytest.mark.integration


def test_admin_page_served(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    assert b"Admin" in resp.data


def test_admin_api_requires_auth(app_client):
    for path in (
        "/api/admin/dashboard",
        "/api/admin/overview",
        "/api/admin/catalog",
        "/api/admin/users",
        "/api/admin/fetch-runs",
        "/api/admin/config",
    ):
        resp = app_client.get(path)
        assert resp.status_code == 401, path


def test_admin_api_forbidden_for_non_admin(app_client, db):
    from relocation_jobs.db import create_user

    create_user("regular", generate_password_hash("regularpass1"))
    login = app_client.post(
        "/api/auth/login",
        json={"username": "regular", "password": "regularpass1"},
    )
    assert login.status_code == 200
    assert login.get_json()["user"]["is_admin"] is False

    resp = app_client.get("/api/admin/overview")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "Admin access required"


def test_auth_status_includes_is_admin(auth_client):
    resp = auth_client.get("/api/auth/status")
    body = resp.get_json()
    assert body["authenticated"] is True
    assert body["user"]["is_admin"] is True


def test_admin_overview(auth_client, seeded_catalog):
    resp = auth_client.get("/api/admin/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["users"] >= 1
    assert "catalog" in body
    assert "tracking" in body
    assert "fetch" in body
    assert body["catalog"]["companies"] >= 1


def test_admin_dashboard(auth_client, seeded_catalog):
    resp = auth_client.get("/api/admin/dashboard?limit=10")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["overview"]["catalog"]["companies"] >= 1
    assert body["catalog"]["has_data"] is True
    assert isinstance(body["users"]["users"], list)
    assert isinstance(body["runs"]["runs"], list)
    assert body["config"]["database"] == "postgres"


def test_admin_catalog(auth_client, seeded_catalog):
    resp = auth_client.get("/api/admin/catalog")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["has_data"] is True
    assert body["totals"]["companies"] >= 1
    assert "stored_jobs" in body["totals"]
    assert isinstance(body["countries"], list)
    assert isinstance(body["by_ats"], list)
    uk = next(c for c in body["countries"] if c["country"] == "uk")
    assert "stored_jobs" in uk
    uk_meta = next(m for m in body["country_meta"] if m["country"] == "uk")
    assert uk_meta["last_fetch"]
    assert "catalog_imported" in uk_meta


def test_admin_users_lists_bootstrap_admin(auth_client, db):
    resp = auth_client.get("/api/admin/users")
    assert resp.status_code == 200
    users = resp.get_json()["users"]
    assert len(users) >= 1
    admin = next(u for u in users if u["username"] == "admin")
    assert admin["is_admin"] is True


def test_admin_fetch_runs(auth_client, db, test_user):
    from relocation_jobs.db import record_fetch_run

    record_fetch_run(
        user_id=test_user["id"],
        country="uk",
        company_name=None,
        started_at="2026-06-21T10:00:00+00:00",
        finished_at="2026-06-21T10:05:00+00:00",
        exit_code=0,
        new_jobs=3,
        concurrency=8,
        companies_done=5,
        companies_total=5,
        result_line="done",
    )

    resp = auth_client.get("/api/admin/fetch-runs?limit=10")
    assert resp.status_code == 200
    runs = resp.get_json()["runs"]
    assert len(runs) >= 1
    assert runs[0]["username"] == "testuser"
    assert runs[0]["country"] == "uk"


def test_admin_config(auth_client):
    resp = auth_client.get("/api/admin/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["database"] == "postgres"
    assert isinstance(body["include_keywords"], list)
    assert isinstance(body["exclude_keywords"], list)
    assert body["known_ats_count"] > 0


def test_country_fetch_requires_admin(app_client, db, seeded_catalog, monkeypatch):
    from relocation_jobs.db import create_user

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    import relocation_jobs.panel_server as ps

    monkeypatch.setattr(ps, "HTTPX_AVAILABLE", True)
    create_user("regular", generate_password_hash("regularpass12"))
    login = app_client.post(
        "/api/auth/login",
        json={"username": "regular", "password": "regularpass12"},
    )
    assert login.status_code == 200

    resp = app_client.post("/api/fetch", json={"country": "uk", "concurrency": 2})
    assert resp.status_code == 403

    history = app_client.get("/api/fetch/history?country=uk")
    assert history.status_code == 403


def test_admin_country_fetch(auth_client, seeded_catalog, monkeypatch):
    import relocation_jobs.panel_server as ps

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    monkeypatch.setattr(ps, "HTTPX_AVAILABLE", True)
    monkeypatch.setattr(ps, "_start_scrape_thread", lambda *a, **k: None)

    resp = auth_client.post("/api/fetch", json={"country": "uk", "concurrency": 2})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
