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
    assert payload.get("board_pinned") is True

    board2 = v2_auth_client.get("/api/board?country=uk&sort=newest").get_json()
    assert board2["companies"][0]["name"] == co["name"]
    assert board2["companies"][0]["board_pinned"] is True
    pinned_jobs = [j for j in board2["companies"][0]["jobs"] if j["url"] == job["url"]]
    assert len(pinned_jobs) == 1
    assert pinned_jobs[0]["pinned"] is True


def test_pin_replaces_previous_company_pin(v2_auth_client, seeded_catalog_v2):
    from relocation_jobs.catalog.repo import sync_company_board_to_catalog

    sync_company_board_to_catalog(
        "uk",
        {
            "name": "Second Pin Co",
            "city": "London",
            "size": "51-200",
            "careers_url": "https://boards.greenhouse.io/secondpin",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/secondpin",
            "matching_jobs": [
                {
                    "title": "Platform Engineer",
                    "url": "https://boards.greenhouse.io/secondpin/jobs/1",
                    "fetched": "2025-06-10T12:00:00+00:00",
                }
            ],
        },
    )

    first = next(
        c for c in v2_auth_client.get("/api/board?country=uk").get_json()["companies"]
        if c["name"] == "Acme Backend Ltd"
    )
    first_job = first["jobs"][0]
    v2_auth_client.post(
        "/api/jobs/pin",
        json={"country": "uk", "company": first["name"], "url": first_job["url"], "pinned": True},
    )

    second = next(
        c for c in v2_auth_client.get("/api/board?country=uk").get_json()["companies"]
        if c["name"] == "Second Pin Co"
    )
    second_job = second["jobs"][0]
    v2_auth_client.post(
        "/api/jobs/pin",
        json={"country": "uk", "company": second["name"], "url": second_job["url"], "pinned": True},
    )

    board = v2_auth_client.get("/api/board?country=uk&sort=newest").get_json()
    pinned_companies = [c for c in board["companies"] if c.get("board_pinned")]
    assert len(pinned_companies) == 1
    assert pinned_companies[0]["name"] == "Second Pin Co"

    first_again = next(c for c in board["companies"] if c["name"] == first["name"])
    assert first_again.get("board_pinned") is not True
