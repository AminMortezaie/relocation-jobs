from __future__ import annotations

from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.mcp import service

from tests.mcp.conftest import GO_MASTER_TEX
from tests.mcp.test_mcp_service import JOB_URL

COMPANY = "Acme Backend Ltd"
COUNTRY = "uk"
FAKE_PDF = b"%PDF-1.4 test"


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

    pdf = v2_auth_client.get(f"/api/mcp/applications/{idem_key}/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data == FAKE_PDF

    detail = v2_auth_client.get(f"/api/mcp/applications/{idem_key}")
    assert detail.status_code == 200
    assert detail.get_json()["has_pdf"] is True


def test_company_applications_routes_require_auth(v2_client):
    assert v2_client.get("/api/mcp/companies/uk/acme/applications").status_code == 401
    assert v2_client.get("/api/mcp/applications/some-key/tex").status_code == 401


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
