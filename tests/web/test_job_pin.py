from __future__ import annotations

ACME = "Acme Backend Ltd"


def _acme(board: dict) -> dict:
    return next(c for c in board["companies"] if c["name"] == ACME)


def test_pin_job_persists_on_board(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = _acme(board)
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
    acme = _acme(board2)
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
    older = _acme(v2_auth_client.get("/api/board?country=uk").get_json())
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
    acme = _acme(board)
    assert acme["jobs"][0]["pinned"] is True


def test_unpin_job_clears_pin_on_board(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = _acme(board)
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
    assert pin.get_json().get("pinned") is True

    unpin = v2_auth_client.patch(
        "/api/jobs/pin",
        json={
            "country": "uk",
            "company": co["name"],
            "url": job["url"],
            "pinned": False,
        },
    )
    assert unpin.status_code == 200
    assert unpin.get_json().get("pinned") is False

    board2 = v2_auth_client.get("/api/board?country=uk").get_json()
    acme = _acme(board2)
    target = next(j for j in acme["jobs"] if j["url"] == job["url"])
    assert target["pinned"] is False
    assert not [j for j in acme["jobs"] if j.get("pinned")]


def test_hide_not_for_me_does_not_pin_job(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = _acme(board)
    job = co["jobs"][0]

    hide = v2_auth_client.post(
        "/api/jobs/not-for-me",
        json={
            "country": "uk",
            "company": co["name"],
            "url": job["url"],
            "not_for_me": True,
        },
    )
    assert hide.status_code == 200

    board2 = v2_auth_client.get("/api/board?country=uk").get_json()
    acme = _acme(board2)
    hidden = next(j for j in acme["not_for_me_jobs"] if j["url"] == job["url"])
    assert hidden["not_for_me"] is True
    assert not hidden.get("pinned")


def test_pin_allows_multiple_pins_in_same_company(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = _acme(board)
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
    acme = _acme(board2)
    pinned_urls = {j["url"] for j in acme["jobs"] if j.get("pinned")}
    assert pinned_urls == {first_job["url"], second_job["url"]}


def test_unpin_one_job_keeps_other_pins(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = _acme(board)
    first_job, second_job = co["jobs"][0], co["jobs"][1]

    v2_auth_client.post(
        "/api/jobs/pin",
        json={"country": "uk", "company": co["name"], "url": first_job["url"], "pinned": True},
    )
    v2_auth_client.post(
        "/api/jobs/pin",
        json={"country": "uk", "company": co["name"], "url": second_job["url"], "pinned": True},
    )
    v2_auth_client.patch(
        "/api/jobs/pin",
        json={"country": "uk", "company": co["name"], "url": first_job["url"], "pinned": False},
    )

    board2 = v2_auth_client.get("/api/board?country=uk").get_json()
    acme = _acme(board2)
    pinned_urls = {j["url"] for j in acme["jobs"] if j.get("pinned")}
    assert pinned_urls == {second_job["url"]}
