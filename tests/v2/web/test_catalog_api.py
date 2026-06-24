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
