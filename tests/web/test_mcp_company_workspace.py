from __future__ import annotations

from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.mcp import service

from tests.mcp.conftest import GO_MASTER_TEX
from tests.mcp.test_mcp_service import JOB_URL

COMPANY = "Acme Backend Ltd"
COUNTRY = "uk"
FAKE_PDF = b"%PDF-1.4 test"
JOB_URL_B = "https://boards.greenhouse.io/acmebackend/jobs/789012?gh_jid=789012"


def test_list_company_applications_merges_catalog_and_mcp(
    seeded_catalog_v2, mcp_documents,
):
    saved = service.save_tailored_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    idem_key = saved["idempotency_key"]
    mcp_repo.save_pdf(1, idem_key, FAKE_PDF)

    payload = service.list_company_applications(COUNTRY, COMPANY, user_id=1)
    assert payload.company == COMPANY
    assert payload.company_slug == "acme-backend-ltd"
    assert payload.positions
    match = next(p for p in payload.positions if p.idempotency_key == idem_key)
    assert match.has_tailored_tex is True
    assert match.has_pdf is True
    assert match.master_resume_slug == "go"
    assert match.pdf_filename == "test_user_acme_backend_ltd.pdf"
    assert match.has_cover_letter_tex is False
    assert match.has_cover_letter_pdf is False


def test_list_company_applications_includes_cover_letter_flags(
    seeded_catalog_v2, mcp_documents,
):
    saved = service.save_cover_letter_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        r"\documentclass{article}\begin{document}Cover\end{document}",
        user_id=1,
    )
    idem_key = saved["idempotency_key"]
    mcp_repo.save_cover_letter_pdf(1, idem_key, FAKE_PDF)

    payload = service.list_company_applications(COUNTRY, COMPANY, user_id=1)
    match = next(p for p in payload.positions if p.idempotency_key == idem_key)
    assert match.has_cover_letter_tex is True
    assert match.has_cover_letter_pdf is True
    assert match.cover_letter_pdf_filename == "test_user_acme_backend_ltd_cover_letter.pdf"
    assert match.has_tailored_tex is False
    assert match.has_pdf is False


def test_list_company_applications_excludes_not_for_me(
    v2_auth_client, seeded_catalog_v2, mcp_documents,
):
    from relocation_jobs.catalog.repo import get_company

    company = get_company("uk", COMPANY)
    visible_url = company["matching_jobs"][0]["url"]
    hidden_url = company["matching_jobs"][1]["url"]
    v2_auth_client.post(
        "/api/jobs/not-for-me",
        json={
            "country": COUNTRY,
            "company": COMPANY,
            "url": hidden_url,
            "not_for_me": True,
        },
    )

    payload = service.list_company_applications(COUNTRY, COMPANY, user_id=1)
    urls = {p.url for p in payload.positions}
    assert visible_url in urls
    assert hidden_url not in urls


def test_list_company_applications_resolves_slug(
    seeded_catalog_v2, mcp_documents,
):
    payload = service.list_company_applications(
        COUNTRY,
        "acme-backend-ltd",
        user_id=1,
    )
    assert payload.company == COMPANY


def test_list_company_applications_resolves_case_insensitive_slug(
    seeded_catalog_v2, mcp_documents,
):
    saved = service.save_tailored_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    payload = service.list_company_applications(
        COUNTRY,
        "acme-backend-ltd",
        user_id=1,
    )
    match = next(p for p in payload.positions if p.idempotency_key == saved["idempotency_key"])
    assert match.has_tailored_tex is True


def test_read_application_tex_and_pdf(seeded_catalog_v2, mcp_documents):
    saved = service.save_tailored_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    idem_key = saved["idempotency_key"]
    mcp_repo.save_pdf(1, idem_key, FAKE_PDF)

    tex = service.read_application_tex(idem_key, user_id=1)
    assert "documentclass" in tex.content
    assert tex.master_resume_slug == "go"

    pdf = service.read_application_pdf(idem_key, user_id=1)
    assert pdf == FAKE_PDF


def test_save_application_tex_updates_content(seeded_catalog_v2, mcp_documents):
    saved = service.save_tailored_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    idem_key = saved["idempotency_key"]
    updated_tex = GO_MASTER_TEX.replace("Go Backend Engineer", "Senior Go Developer")

    result = service.save_application_tex(idem_key, updated_tex, user_id=1)
    assert result["ok"] is True
    assert result["updated_at"]

    tex = service.read_application_tex(idem_key, user_id=1)
    assert "Senior Go Developer" in tex.content


def test_position_description_api(v2_auth_client, seeded_catalog_v2, mcp_documents):
    from relocation_jobs.catalog.repo import get_company, sync_company_board_to_catalog

    company = get_company("uk", COMPANY)
    assert company is not None
    jobs = list(company["matching_jobs"])
    jobs[0]["description_text"] = "Build APIs and mentor engineers."
    company["matching_jobs"] = jobs
    sync_company_board_to_catalog(COUNTRY, company)

    saved = service.save_tailored_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    idem_key = saved["idempotency_key"]

    detail = v2_auth_client.get(f"/api/mcp/positions/{idem_key}/description")
    assert detail.status_code == 200
    body = detail.get_json()
    assert body["has_description"] is True
    assert body["needs_fetch"] is False
    assert "Build APIs" in body["description_text"]
    assert "<p>" in body["description_html"]
    assert body["company"] == COMPANY

    list_payload = service.list_company_applications(COUNTRY, COMPANY, user_id=1)
    match = next(p for p in list_payload.positions if p.idempotency_key == idem_key)
    assert match.has_description is True


def test_position_description_needs_fetch_when_empty(
    v2_auth_client, seeded_catalog_v2, mcp_documents,
):
    from relocation_jobs.catalog.repo import get_company

    company = get_company(COUNTRY, COMPANY)
    second = company["matching_jobs"][1]
    detail = v2_auth_client.get(
        f"/api/mcp/positions/{second['idempotency_key']}/description",
    )
    assert detail.status_code == 200
    body = detail.get_json()
    assert body["has_description"] is False
    assert body["needs_fetch"] is True


def test_position_fetch_description_stores_text(
    v2_auth_client, seeded_catalog_v2, mcp_documents, monkeypatch,
):
    from relocation_jobs.catalog.repo import get_company

    company = get_company(COUNTRY, COMPANY)
    second = company["matching_jobs"][1]
    idem_key = second["idempotency_key"]
    job_url = second["url"]

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    monkeypatch.setattr("relocation_jobs.web.routes.mcp.HTTPX_AVAILABLE", True)

    def fake_fetch(url, ats_type=None):
        assert url == job_url
        return "Senior backend role with Go, Postgres, and distributed systems."

    monkeypatch.setattr(
        "relocation_jobs.mcp.service.fetch_job_description",
        fake_fetch,
    )

    fetched = v2_auth_client.post(f"/api/mcp/positions/{idem_key}/fetch-description")
    assert fetched.status_code == 200
    body = fetched.get_json()
    assert body["has_description"] is True
    assert body["needs_fetch"] is False
    assert "distributed systems" in body["description_text"]


def test_company_applications_api(v2_auth_client, seeded_catalog_v2, mcp_documents):
    saved = service.save_tailored_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    idem_key = saved["idempotency_key"]
    mcp_repo.save_pdf(1, idem_key, FAKE_PDF)

    by_name = v2_auth_client.get(
        f"/api/mcp/companies/{COUNTRY}/{COMPANY}/applications",
    )
    assert by_name.status_code == 200
    body = by_name.get_json()
    assert body["company_slug"] == "acme-backend-ltd"
    assert any(p["has_pdf"] for p in body["positions"])

    by_slug = v2_auth_client.get(
        f"/api/mcp/companies/{COUNTRY}/acme-backend-ltd/applications",
    )
    assert by_slug.status_code == 200
    assert by_slug.get_json()["company"] == COMPANY

    tex = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/tex")
    assert tex.status_code == 200
    assert "documentclass" in tex.get_json()["content"]

    updated_tex = GO_MASTER_TEX.replace("Go Backend Engineer", "Staff Go Developer")
    saved_tex = v2_auth_client.put(
        f"/api/mcp/applications/{idem_key}/tex",
        json={"content": updated_tex},
    )
    assert saved_tex.status_code == 200
    assert saved_tex.get_json()["ok"] is True

    tex_after = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/tex")
    assert "Staff Go Developer" in tex_after.get_json()["content"]

    pdf = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data == FAKE_PDF
    disposition = pdf.headers.get("Content-Disposition") or ""
    assert disposition.startswith("inline;")
    assert "test_user_acme_backend_ltd.pdf" in disposition

    pdf_download = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/pdf?download=1")
    assert pdf_download.status_code == 200
    download_disposition = pdf_download.headers.get("Content-Disposition") or ""
    assert download_disposition.startswith("attachment;")
    assert "test_user_acme_backend_ltd.pdf" in download_disposition

    detail = v2_auth_client.get(f"/api/mcp/applications/{idem_key}")
    assert detail.status_code == 200
    assert detail.get_json()["has_pdf"] is True


def test_list_company_applications_finds_tex_when_country_mixed_case(
    seeded_catalog_v2, mcp_documents,
):
    saved = service.save_tailored_tex_for_job(
        "UK",
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    payload = service.list_company_applications("uk", COMPANY, user_id=1)
    match = next(p for p in payload.positions if p.idempotency_key == saved["idempotency_key"])
    assert match.has_tailored_tex is True
    row = mcp_repo.get_application(1, saved["idempotency_key"])
    assert row is not None
    assert row["country"] == "uk"


def test_company_applications_routes_require_auth(v2_client):
    assert v2_client.get("/api/mcp/companies/uk/acme/applications").status_code == 401
    assert v2_client.get("/api/mcp/positions/some-key/description").status_code == 401
    assert v2_client.post("/api/mcp/positions/some-key/fetch-description").status_code == 401
    assert v2_client.get("/api/mcp/applications/some-key/tex").status_code == 401
    assert v2_client.put("/api/mcp/applications/some-key/tex", json={"content": "x"}).status_code == 401


def test_board_jobs_include_mcp_flags(v2_auth_client, seeded_catalog_v2, mcp_documents):
    saved = service.save_tailored_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    mcp_repo.save_pdf(1, saved["idempotency_key"], FAKE_PDF)

    board = v2_auth_client.get("/api/board?country=uk").get_json()
    acme = next(c for c in board["companies"] if c["name"] == COMPANY)
    job = next(j for j in acme["jobs"] if j["url"] == JOB_URL)
    assert job["has_tailored_tex"] is True
    assert job["has_pdf"] is True
    assert job["master_resume_slug"] == "go"


def test_cover_letter_http_roundtrip(v2_auth_client, seeded_catalog_v2, mcp_documents):
    cover = r"\documentclass{article}\begin{document}Dear hiring manager\end{document}"
    saved = service.save_cover_letter_tex_for_job(
        COUNTRY,
        COMPANY,
        JOB_URL,
        cover,
        user_id=1,
    )
    idem_key = saved["idempotency_key"]
    mcp_repo.save_cover_letter_pdf(1, idem_key, FAKE_PDF)

    listed = v2_auth_client.get(
        f"/api/mcp/companies/{COUNTRY}/{COMPANY}/applications",
    )
    assert listed.status_code == 200
    match = next(p for p in listed.get_json()["positions"] if p["idempotency_key"] == idem_key)
    assert match["has_cover_letter_tex"] is True
    assert match["has_cover_letter_pdf"] is True

    tex = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/cover-letter/tex")
    assert tex.status_code == 200
    assert "Dear hiring manager" in tex.get_json()["content"]

    updated = cover.replace("Dear hiring manager", "Dear team")
    put = v2_auth_client.put(
        f"/api/mcp/applications/{idem_key}/cover-letter/tex",
        json={"content": updated},
    )
    assert put.status_code == 200
    assert put.get_json()["ok"] is True

    tex_after = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/cover-letter/tex")
    assert "Dear team" in tex_after.get_json()["content"]

    pdf = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/cover-letter/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data == FAKE_PDF
    disposition = pdf.headers.get("Content-Disposition") or ""
    assert "test_user_acme_backend_ltd_cover_letter.pdf" in disposition

    board = v2_auth_client.get("/api/board?country=uk").get_json()
    acme = next(c for c in board["companies"] if c["name"] == COMPANY)
    job = next(j for j in acme["jobs"] if j["url"] == JOB_URL)
    assert job["has_cover_letter_tex"] is True
    assert job["has_cover_letter_pdf"] is True


def test_cover_letter_routes_require_auth(v2_client):
    assert v2_client.get("/api/mcp/applications/some-key/cover-letter/tex").status_code == 401
    assert v2_client.put(
        "/api/mcp/applications/some-key/cover-letter/tex",
        json={"content": "x"},
    ).status_code == 401
    assert v2_client.get("/api/mcp/applications/some-key/cover-letter/pdf").status_code == 401
    assert v2_client.post("/api/mcp/applications/some-key/cover-letter/render").status_code == 401
