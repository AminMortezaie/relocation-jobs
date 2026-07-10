from __future__ import annotations


def test_board_returns_catalog_without_panel_filters(v2_auth_client, seeded_catalog_v2):
    resp = v2_auth_client.get("/api/board?country=uk")
    assert resp.status_code == 200
    payload = resp.get_json()
    companies = payload["companies"]
    meta = payload["meta"]
    assert len(companies) == 1
    assert companies[0]["name"] == "Acme Backend Ltd"
    assert len(companies[0]["jobs"]) == 2
    assert meta["country"] == "uk"
    assert "fetch_problem_total" in meta
    assert meta["page"] == 1
    assert meta["page_size"] == 25
    assert meta["total_companies"] == 1
    assert meta["total_pages"] == 1
    assert meta["has_more"] is False
    assert meta["sort"] == "newest"
    assert "positions_applied" in payload["user_stats"]
    assert "recent_fetch_runs" in payload["user_stats"]


def test_board_stats_returns_user_metrics(v2_auth_client, seeded_catalog_v2):
    board = v2_auth_client.get("/api/board?country=uk&timezone=UTC").get_json()
    resp = v2_auth_client.get(
        "/api/board/stats?country=uk&timezone=UTC"
        f"&latest_fetch_new_jobs={board['meta']['latest_fetch_new_jobs']}"
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert "positions_applied" in payload
    assert "positions_applied_today" in payload
    assert "applied_today_jobs" in payload
    assert "recent_fetch_runs" in payload


def test_board_sort_newest_orders_by_latest_job_fetched(v2_auth_client, seeded_catalog_v2):
    from relocation_jobs.catalog.repo import get_company, sync_company_board_to_catalog

    sync_company_board_to_catalog(
        "uk",
        {
            "name": "AAA Older Fetch",
            "city": "London",
            "size": "51-200",
            "careers_url": "https://boards.greenhouse.io/aaaolder",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/aaaolder",
            "matching_jobs": [
                {
                    "title": "Backend Engineer",
                    "url": "https://boards.greenhouse.io/aaaolder/jobs/1?gh_jid=1",
                    "fetched": "2025-06-01T22:49:00+00:00",
                    "last_seen": "2025-06-01T22:49:00+00:00",
                }
            ],
            "updated": "2025-06-10T12:00:00+00:00",
            "added": "2025-06-01",
        },
    )
    acme = get_company("uk", "Acme Backend Ltd")
    assert acme is not None
    jobs = list(acme.get("matching_jobs") or [])
    jobs[0]["fetched"] = "2025-06-02T00:45:00+00:00"
    acme["matching_jobs"] = jobs
    acme["updated"] = "2025-01-01T00:00:00+00:00"
    sync_company_board_to_catalog("uk", acme)

    by_name = v2_auth_client.get("/api/board?country=uk&sort=name").get_json()
    assert [c["name"] for c in by_name["companies"]] == [
        "AAA Older Fetch",
        "Acme Backend Ltd",
    ]

    by_newest = v2_auth_client.get("/api/board?country=uk&sort=newest").get_json()
    assert [c["name"] for c in by_newest["companies"]] == [
        "Acme Backend Ltd",
        "AAA Older Fetch",
    ]
    assert by_newest["meta"]["sort"] == "newest"


def test_board_sort_newest_ignores_not_for_me_job_fetched(v2_auth_client, seeded_catalog_v2):
    from relocation_jobs.catalog.repo import get_company, sync_company_board_to_catalog
    from relocation_jobs.positions import set_job_not_for_me

    sync_company_board_to_catalog(
        "uk",
        {
            "name": "AAA Older Fetch",
            "city": "London",
            "size": "51-200",
            "careers_url": "https://boards.greenhouse.io/aaaolder",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/aaaolder",
            "matching_jobs": [
                {
                    "title": "Backend Engineer",
                    "url": "https://boards.greenhouse.io/aaaolder/jobs/1?gh_jid=1",
                    "fetched": "2025-06-02T00:45:00+00:00",
                    "last_seen": "2025-06-02T00:45:00+00:00",
                }
            ],
            "added": "2025-06-01",
        },
    )
    acme = get_company("uk", "Acme Backend Ltd")
    assert acme is not None
    jobs = list(acme.get("matching_jobs") or [])
    jobs.append(
        {
            "title": "Brand New Role",
            "url": "https://boards.greenhouse.io/acmebackend/jobs/999999?gh_jid=999999",
            "fetched": "2025-06-10T12:00:00+00:00",
            "last_seen": "2025-06-10T12:00:00+00:00",
        },
    )
    acme["matching_jobs"] = jobs
    sync_company_board_to_catalog("uk", acme)
    set_job_not_for_me(
        "uk",
        "Acme Backend Ltd",
        "https://boards.greenhouse.io/acmebackend/jobs/999999?gh_jid=999999",
        user_id=1,
        not_for_me=True,
    )

    by_newest = v2_auth_client.get("/api/board?country=uk&sort=newest").get_json()
    assert [c["name"] for c in by_newest["companies"]] == [
        "AAA Older Fetch",
        "Acme Backend Ltd",
    ]
    acme_row = next(c for c in by_newest["companies"] if c["name"] == "Acme Backend Ltd")
    assert acme_row["newest_job_fetched"].startswith("2025-06-01")


def test_board_panel_filters_still_on_legacy_jobs_route(v2_auth_client, seeded_catalog_v2):
    listing = v2_auth_client.get("/api/jobs?country=uk").get_json()
    company = next(c for c in listing["companies"] if c["name"] == "Acme Backend Ltd")
    job = company["jobs"][0]
    ctx = {"country": "uk", "company": company["name"], "url": job["url"]}
    v2_auth_client.post("/api/jobs/applied", json={**ctx, "applied": True})

    filtered = v2_auth_client.get("/api/jobs?country=uk&position_applied_only=1").get_json()
    assert len(filtered["companies"]) == 1
    assert filtered["companies"][0]["jobs"][0]["applied"] is True

    board = v2_auth_client.get("/api/board?country=uk").get_json()
    acme = next(c for c in board["companies"] if c["name"] == "Acme Backend Ltd")
    assert len(acme["jobs"]) == 2


def test_board_cv_badge_uses_supported_workspace_path_for_unsupported_application_country(
    v2_auth_client, seeded_catalog_v2, mcp_documents,
):
    from relocation_jobs.catalog.repo import sync_company_board_to_catalog
    from relocation_jobs.core.job_identity import job_idempotency_key
    from relocation_jobs.mcp import repo as mcp_repo

    del seeded_catalog_v2, mcp_documents
    germany_url = "https://www.workato.com/careers?gh_jid=8284791002#open-roles"
    singapore_url = "https://workato.com/careers?gh_jid=8284791002"
    idem_key = job_idempotency_key(singapore_url)

    sync_company_board_to_catalog(
        "germany",
        {
            "name": "Workato",
            "city": "Berlin",
            "size": "201-500",
            "careers_url": "https://www.workato.com/careers",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/workato",
            "matching_jobs": [
                {
                    "title": "Senior Software Engineer (Go)",
                    "url": germany_url,
                    "idempotency_key": idem_key,
                    "location": "Singapore",
                    "fetched": "2026-07-09T12:05:09+00:00",
                    "last_seen": "2026-07-09T12:05:09+00:00",
                }
            ],
        },
    )
    sync_company_board_to_catalog(
        "singapore",
        {
            "name": "Workato",
            "city": "Singapore",
            "size": "201-500",
            "careers_url": "https://workato.com/careers",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/workato",
            "matching_jobs": [
                {
                    "title": "Senior Software Engineer (Go)",
                    "url": singapore_url,
                    "idempotency_key": idem_key,
                    "location": "Singapore",
                    "fetched": "2026-07-09",
                    "last_seen": "2026-07-09",
                }
            ],
        },
    )
    mcp_repo.save_tailored_tex(
        1,
        idem_key,
        r"\documentclass{article}\begin{document}Go\end{document}",
        master_resume_slug="go",
        country="singapore",
        company="Workato",
        url=singapore_url,
    )

    summaries = mcp_repo.load_application_summaries(1)
    assert summaries[idem_key]["has_tailored_tex"] is True
    assert summaries[idem_key]["workspace_path"] == "/company/germany/workato"
