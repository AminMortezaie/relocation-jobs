from __future__ import annotations


def test_board_job_has_country_for_click_handler(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = board["companies"][0]
    job = co["jobs"][0]
    assert job.get("country") == "uk"
    assert job.get("company") == co["name"]


def test_mark_seen_api_and_board_reflects(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = board["companies"][0]
    job = co["jobs"][0]
    r = v2_auth_client.post(
        "/api/jobs/seen",
        json={
            "country": job["country"],
            "company": co["name"],
            "url": job["url"],
            "seen": True,
        },
    )
    assert r.status_code == 200
    assert r.get_json().get("seen") is True
    board2 = v2_auth_client.get("/api/board?country=uk").get_json()
    seen_jobs = [j for c in board2["companies"] for j in c["jobs"] if j["url"] == job["url"]]
    assert len(seen_jobs) == 1
    assert seen_jobs[0].get("seen") is True
