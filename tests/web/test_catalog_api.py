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
    from relocation_jobs.users.repo import get_user_by_username
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
    assert "worker" in payload
    assert "panel_stats" in payload
    assert payload["panel_stats"] is None
    assert "catalog" in payload
    assert payload["catalog"]["has_data"] is True
    assert "users" in payload
    assert "runs" in payload
    assert "config" in payload
    assert "overview" not in payload


def test_admin_panel_stats(v2_auth_client, seeded_catalog_v2):
    resp = v2_auth_client.get("/api/admin/panel-stats?country=uk&timezone=UTC")
    assert resp.status_code == 200
    stats = resp.get_json()
    assert stats["total_jobs"] == 2
    assert stats["companies_with_jobs"] == 1
    assert "positions_applied" in stats
    assert "positions_not_for_me" in stats
    assert stats["positions_not_for_me"] == 0


def test_admin_panel_stats_open_roles_exclude_applied_and_not_for_me(
    v2_auth_client, seeded_catalog_v2,
):
    from relocation_jobs.positions import set_job_not_for_me

    listing = v2_auth_client.get("/api/jobs?country=uk").get_json()
    company = listing["companies"][0]["name"]
    jobs = listing["companies"][0]["jobs"]

    set_job_not_for_me("uk", company, jobs[0]["url"], user_id=1, not_for_me=True)
    v2_auth_client.post(
        "/api/jobs/applied",
        json={
            "country": "uk",
            "company": company,
            "url": jobs[1]["url"],
            "applied": True,
        },
    )

    stats = v2_auth_client.get("/api/admin/panel-stats?country=uk&timezone=UTC").get_json()
    assert stats["total_jobs"] == 0
    assert stats["companies_with_jobs"] == 0
    assert stats["positions_applied"] == 1
    assert stats["positions_not_for_me"] == 1


def test_admin_panel_stats_new_jobs_today_from_fetch_runs(v2_auth_client, seeded_catalog_v2):
    from datetime import datetime, timezone

    from relocation_jobs.users.repo import get_user_by_username
    from relocation_jobs.fetch import repo as fetch_repo

    user_id = get_user_by_username("admin")["id"]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    started = now.isoformat()
    finished = now.isoformat()
    run_id = int(fetch_repo.create_fetch_run(
        user_id=user_id,
        country="uk",
        company_name=None,
        file_name="uk.json",
        concurrency=1,
        started_at=started,
    )["id"])
    fetch_repo.finalize_fetch_run(
        run_id,
        finished_at=finished,
        exit_code=0,
        new_jobs=4,
        companies_done=1,
        companies_total=1,
        result_line="Done",
    )
    run_id = int(fetch_repo.create_fetch_run(
        user_id=user_id,
        country="uk",
        company_name="Acme Backend Ltd",
        file_name="uk.json",
        concurrency=1,
        started_at=started,
    )["id"])
    fetch_repo.finalize_fetch_run(
        run_id,
        finished_at=finished,
        exit_code=0,
        new_jobs=2,
        companies_done=1,
        companies_total=1,
        result_line="Done",
    )

    stats = v2_auth_client.get("/api/admin/panel-stats?country=uk&timezone=UTC").get_json()
    assert stats["latest_fetch_new_jobs"] == 6


def test_countries_list_includes_custom_country(v2_auth_client, tmp_data_dir):
    created = v2_auth_client.post("/api/countries", json={"label": "Spain"}).get_json()
    assert created["ok"] is True
    assert created["country"] == {"id": "spain", "label": "Spain"}

    countries = v2_auth_client.get("/api/countries").get_json()
    ids = {item["id"] for item in countries}
    assert "spain" in ids


def test_locations_picker_returns_structured_list(v2_auth_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_auth_client.get("/api/locations?country=all&picker=1")
    assert resp.status_code == 200
    locations = resp.get_json()["locations"]
    assert isinstance(locations, list)
    for loc in locations:
        assert "country" in loc
        assert "city" in loc
        assert "key" in loc


def test_add_custom_city_requires_supported_country(v2_auth_client, tmp_data_dir):
    resp = v2_auth_client.post("/api/locations", json={"country": "spain", "city": "Madrid"})
    assert resp.status_code == 400

    v2_auth_client.post("/api/countries", json={"label": "Spain"})
    saved = v2_auth_client.post(
        "/api/locations",
        json={"country": "spain", "city": "Madrid"},
    ).get_json()
    assert saved["ok"] is True
    assert saved["location"]["city"] == "Madrid"
