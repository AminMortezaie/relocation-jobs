from __future__ import annotations


def test_panel_page_keeps_private_app_shell(v2_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_client.get("/panel")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="loginPanel"' in body
    assert 'src="/static/js/main.js' in body


def test_public_preview_page_is_available_without_auth(v2_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<title>Relocation Jobs" in body
    assert "Find visa-sponsored" in body
    assert "track applications" in body
    assert "/panel" in body


def test_legacy_preview_path_redirects_to_root(v2_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_client.get("/preview", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/")


def test_legacy_app_path_redirects_to_panel(v2_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_client.get("/app", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/panel")


def test_public_overview_returns_catalog_snapshot(v2_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_client.get("/api/public/overview")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["has_data"] is True
    assert payload["totals"]["companies"] >= 1
    assert payload["totals"]["jobs"] >= 2
    assert payload["countries"]
    uk = next(row for row in payload["countries"] if row["country"] == "uk")
    assert uk["companies"] >= 1
    assert uk["jobs"] >= 2
    assert "country_meta" in payload


def test_public_preview_returns_company_sample_without_user_state(v2_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_client.get("/api/public/preview")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["companies"]
    company = payload["companies"][0]
    assert "name" in company
    assert "job_count" in company
    assert "preview_jobs" not in company
    assert "positions_applied" not in company
    assert "title" not in str(payload["companies"])


def test_public_preview_accepts_country_and_query_filters(v2_client, seeded_catalog_v2):
    del seeded_catalog_v2
    resp = v2_client.get("/api/public/preview?country=uk&limit=12")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["meta"]["country"] == "uk"
    assert all(row["country"] == "uk" for row in payload["companies"])


def test_public_seo_endpoints_are_available(v2_client):
    robots = v2_client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Sitemap:" in robots.get_data(as_text=True)

    sitemap = v2_client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "<loc>https://kuchup.com/</loc>" in sitemap.get_data(as_text=True)


def test_unknown_country_marketing_path_returns_404(v2_client):
    resp = v2_client.get("/relocation-jobs-no-such-country")
    assert resp.status_code == 404


def test_country_marketing_path_requires_label_and_html(v2_client, monkeypatch, tmp_path):
    from relocation_jobs.web import server as web_server

    html_dir = tmp_path / "homepage"
    html_dir.mkdir()
    (html_dir / "relocation-jobs-armenia.html").write_text("<html>armenia</html>", encoding="utf-8")
    monkeypatch.setattr(web_server, "HOMEPAGE_STATIC", html_dir)
    monkeypatch.setattr(
        web_server,
        "all_country_labels",
        lambda: {"armenia": "Armenia", "germany": "Germany"},
    )

    missing_html = v2_client.get("/relocation-jobs-germany")
    assert missing_html.status_code == 404

    ok = v2_client.get("/relocation-jobs-armenia")
    assert ok.status_code == 200
    assert "armenia" in ok.get_data(as_text=True)

    sitemap = v2_client.get("/sitemap.xml")
    body = sitemap.get_data(as_text=True)
    assert "<loc>https://kuchup.com/relocation-jobs-armenia</loc>" in body
    assert "relocation-jobs-germany" not in body
