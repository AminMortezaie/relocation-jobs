from __future__ import annotations


def test_jobs_list_returns_companies(v2_auth_client, seeded_catalog_v2):
    resp = v2_auth_client.get("/api/jobs?country=uk")
    assert resp.status_code == 200
    payload = resp.get_json()
    companies = payload["companies"]
    stats = payload["stats"]
    assert len(companies) == 1
    assert companies[0]["name"] == "Acme Backend Ltd"
    assert len(companies[0]["jobs"]) == 2
    assert stats["total_jobs"] == 2
    assert stats["companies_with_jobs"] == 1


def test_jobs_applied_marks_position(v2_auth_client, seeded_catalog_v2):
    listing = v2_auth_client.get("/api/jobs?country=uk").get_json()
    company = listing["companies"][0]
    job = company["jobs"][0]
    ctx = {"country": "uk", "company": company["name"], "url": job["url"]}
    resp = v2_auth_client.post("/api/jobs/applied", json={**ctx, "applied": True})
    assert resp.status_code == 200
    assert resp.get_json()["applied"] is True

    refreshed = v2_auth_client.get("/api/jobs?country=uk&position_applied_only=1").get_json()
    assert len(refreshed["companies"]) == 1
    assert refreshed["companies"][0]["jobs"][0]["applied"] is True
