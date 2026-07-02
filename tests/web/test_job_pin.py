from __future__ import annotations


def test_pin_job_persists_on_board(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = board["companies"][0]
    job = co["jobs"][0]

    pin = v2_auth_client.post(
        "/api/jobs/pin",
        json={
            "country": "uk",
            "company": co["name"],
            "url": job["url"],
            "pinned": True,
        },
    )
    assert pin.status_code == 200
    payload = pin.get_json()
    assert payload.get("pinned") is True
    assert not payload.get("board_pinned")

    board2 = v2_auth_client.get("/api/board?country=uk&sort=newest").get_json()
    acme = next(c for c in board2["companies"] if c["name"] == co["name"])
    assert not acme.get("board_pinned")
    pinned_jobs = [j for j in acme["jobs"] if j["url"] == job["url"]]
    assert len(pinned_jobs) == 1
    assert pinned_jobs[0]["pinned"] is True
    assert acme["jobs"][0]["url"] == job["url"]


def test_pin_does_not_reorder_company_on_board(v2_auth_client, seeded_catalog_v2):
    from relocation_jobs.catalog.repo import sync_company_board_to_catalog

    sync_company_board_to_catalog(
        "uk",
        {
            "name": "Newer Jobs Co",
            "city": "London",
            "size": "51-200",
            "careers_url": "https://boards.greenhouse.io/newerjobs",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/newerjobs",
            "matching_jobs": [
                {
                    "title": "Platform Engineer",
                    "url": "https://boards.greenhouse.io/newerjobs/jobs/1",
                    "fetched": "2025-06-10T12:00:00+00:00",
                }
            ],
        },
    )
    older = next(
        c for c in v2_auth_client.get("/api/board?country=uk").get_json()["companies"]
        if c["name"] == "Acme Backend Ltd"
    )
    older_job = older["jobs"][0]
    v2_auth_client.post(
        "/api/jobs/pin",
        json={
            "country": "uk",
            "company": older["name"],
            "url": older_job["url"],
            "pinned": True,
        },
    )

    board = v2_auth_client.get("/api/board?country=uk&sort=newest").get_json()
    assert board["companies"][0]["name"] == "Newer Jobs Co"
    acme = next(c for c in board["companies"] if c["name"] == "Acme Backend Ltd")
    assert acme["jobs"][0]["pinned"] is True


def test_pin_replaces_previous_job_pin_in_same_company(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = board["companies"][0]
    first_job, second_job = co["jobs"][0], co["jobs"][1]

    v2_auth_client.post(
        "/api/jobs/pin",
        json={"country": "uk", "company": co["name"], "url": first_job["url"], "pinned": True},
    )
    v2_auth_client.post(
        "/api/jobs/pin",
        json={"country": "uk", "company": co["name"], "url": second_job["url"], "pinned": True},
    )

    board2 = v2_auth_client.get("/api/board?country=uk").get_json()
    acme = next(c for c in board2["companies"] if c["name"] == co["name"])
    pinned_jobs = [j for j in acme["jobs"] if j.get("pinned")]
    assert len(pinned_jobs) == 1
    assert pinned_jobs[0]["url"] == second_job["url"]
