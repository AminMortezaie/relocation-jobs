from __future__ import annotations


def _login(client, username: str, password: str):
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200


def test_remove_country_full_purge(v2_auth_client, seeded_catalog_v2, db):
    from relocation_jobs.core.db import db_read
    from relocation_jobs.core.job_identity import job_idempotency_key, stamp_job_identity
    from relocation_jobs.fetch import repo as fetch_repo
    from relocation_jobs.mcp import repo as mcp_repo
    from relocation_jobs.positions import set_job_applied
    from relocation_jobs.users.repo import get_user_by_username

    del db
    user_id = get_user_by_username("admin")["id"]
    listing = v2_auth_client.get("/api/jobs?country=uk").get_json()
    company = listing["companies"][0]["name"]
    job_url = listing["companies"][0]["jobs"][0]["url"]
    set_job_applied("uk", company, job_url, user_id=user_id, applied=True)

    fetch_repo.create_fetch_run(
        user_id=user_id,
        country="uk",
        company_name=None,
        file_name="uk.json",
        concurrency=1,
        started_at="2025-06-01T12:00:00+00:00",
    )

    job = listing["companies"][0]["jobs"][0]
    stamp_job_identity(job)
    key = job.get("idempotency_key") or job_idempotency_key(job["url"])
    mcp_repo.upsert_application_shell(
        user_id,
        key,
        country="uk",
        company=company,
        url=job_url,
    )

    resp = v2_auth_client.delete("/api/countries/uk")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["country"] == "uk"
    assert payload["removed_companies"] >= 1
    assert payload["removed_jobs"] >= 1
    assert payload["removed_job_tracking"] >= 1
    assert payload["removed_fetch_runs"] >= 1
    assert payload["removed_mcp_applications"] >= 1

    countries = v2_auth_client.get("/api/countries").get_json()
    ids = {item["id"] for item in countries}
    assert "uk" not in ids

    with db_read() as conn:
        companies = conn.execute(
            "SELECT COUNT(*) AS n FROM companies WHERE country = %s",
            ("uk",),
        ).fetchone()
        tracking = conn.execute(
            "SELECT COUNT(*) AS n FROM job_tracking WHERE country = %s",
            ("uk",),
        ).fetchone()
        runs = conn.execute(
            "SELECT COUNT(*) AS n FROM fetch_runs WHERE country = %s",
            ("uk",),
        ).fetchone()
        apps = conn.execute(
            "SELECT COUNT(*) AS n FROM mcp_applications WHERE country = %s",
            ("uk",),
        ).fetchone()
    assert int(companies["n"]) == 0
    assert int(tracking["n"]) == 0
    assert int(runs["n"]) == 0
    assert int(apps["n"]) == 0


def test_remove_country_post_alias(v2_auth_client, seeded_catalog_v2, db):
    del db
    resp = v2_auth_client.post("/api/countries/remove", json={"country": "uk"})
    assert resp.status_code == 200
    assert resp.get_json()["country"] == "uk"


def test_remove_country_requires_admin(v2_client, test_user, seeded_catalog_v2, db):
    del db
    _login(v2_client, "testuser", "testpass123")
    resp = v2_client.delete("/api/countries/uk")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "Admin access required"


def test_remove_country_blocks_active_fetch(v2_auth_client, seeded_catalog_v2, monkeypatch):
    from relocation_jobs.fetch import state as fetch_state

    monkeypatch.setattr(
        fetch_state,
        "memory_status",
        lambda: {"running": True, "country": "uk"},
    )
    resp = v2_auth_client.delete("/api/countries/uk")
    assert resp.status_code == 409
    assert "Fetch is running" in resp.get_json()["error"]


def test_remove_custom_country_without_catalog(v2_auth_client, tmp_data_dir):
    v2_auth_client.post("/api/countries", json={"label": "Spain"})
    resp = v2_auth_client.delete("/api/countries/spain")
    assert resp.status_code == 200
    countries = v2_auth_client.get("/api/countries").get_json()
    ids = {item["id"] for item in countries}
    assert "spain" not in ids


def test_admin_dashboard_lists_registered_country_without_catalog(v2_auth_client, tmp_data_dir):
    v2_auth_client.post("/api/countries", json={"label": "Singapore"})
    dashboard = v2_auth_client.get("/api/admin/dashboard?limit=10").get_json()
    catalog = dashboard["catalog"]
    ids = {row["country"] for row in catalog["countries"]}
    assert "singapore" in ids
    singapore = next(row for row in catalog["countries"] if row["country"] == "singapore")
    assert singapore["companies"] == 0
    assert singapore["jobs"] == 0
