from __future__ import annotations

from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.mcp import service

FAKE_PDF = b"%PDF-1.4 test"


def test_mcp_profile_round_trip(v2_auth_client):
    empty = v2_auth_client.get("/api/mcp/profile")
    assert empty.status_code == 200
    assert empty.get_json()["profile"]["full_name"] == ""
    assert empty.get_json()["profile"]["pipeline"] == []

    saved = v2_auth_client.put(
        "/api/mcp/profile",
        json={
            "full_name": "Jane Applicant",
            "email": "jane@example.com",
            "phone": "+1 555 0100",
            "linkedin_url": "https://linkedin.com/in/jane",
            "location": "Amsterdam",
            "work_authorization": "EU citizen",
            "notice_period": "4 weeks",
            "summary": "Backend engineer",
            "pipeline": [
                "Emphasize distributed systems experience.",
                "Keep the resume under two pages.",
            ],
        },
    )
    assert saved.status_code == 200
    payload = saved.get_json()
    assert payload["ok"] is True
    assert payload["profile"]["full_name"] == "Jane Applicant"
    assert payload["profile"]["pipeline"] == [
        "Emphasize distributed systems experience.",
        "Keep the resume under two pages.",
    ]

    loaded = v2_auth_client.get("/api/mcp/profile")
    assert loaded.status_code == 200
    assert loaded.get_json()["profile"]["email"] == "jane@example.com"
    assert len(loaded.get_json()["profile"]["pipeline"]) == 2


def test_mcp_profile_pipeline_max_five(v2_auth_client):
    resp = v2_auth_client.put(
        "/api/mcp/profile",
        json={
            "full_name": "Jane",
            "pipeline": [f"prompt {i}" for i in range(6)],
        },
    )
    assert resp.status_code == 400


def test_mcp_master_resume_round_trip(v2_auth_client):
    tex = r"""
\documentclass{article}
\begin{document}
Hello world
\end{document}
"""
    saved = v2_auth_client.put(
        "/api/mcp/master-resumes/fullstack",
        json={"content": tex, "label": "Full stack"},
    )
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["ok"] is True
    assert body["slug"] == "fullstack"
    assert body["label"] == "Full stack"

    listing = v2_auth_client.get("/api/mcp/master-resumes")
    assert listing.status_code == 200
    items = listing.get_json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "fullstack"
    assert items[0]["label"] == "Full stack"

    detail = v2_auth_client.get("/api/mcp/master-resumes/fullstack")
    assert detail.status_code == 200
    detail_body = detail.get_json()
    assert "Hello world" in detail_body["content"]
    assert detail_body["has_pdf"] is False
    assert detail_body["pdf_filename"] == "resume_fullstack.pdf"


def test_mcp_master_resume_pdf_round_trip(v2_auth_client):
    tex = r"""
\documentclass{article}
\begin{document}
Hello world
\end{document}
"""
    saved = v2_auth_client.put(
        "/api/mcp/master-resumes/go",
        json={"content": tex, "label": "Go backend"},
    )
    assert saved.status_code == 200
    slug = saved.get_json()["slug"]
    mcp_repo.save_master_pdf(1, slug, FAKE_PDF)

    listing = v2_auth_client.get("/api/mcp/master-resumes")
    assert listing.status_code == 200
    item = next(i for i in listing.get_json()["items"] if i["slug"] == slug)
    assert item["has_pdf"] is True
    assert item["pdf_filename"] == "resume_go.pdf"

    detail = v2_auth_client.get(f"/api/mcp/master-resumes/{slug}")
    assert detail.status_code == 200
    assert detail.get_json()["has_pdf"] is True

    pdf = v2_auth_client.get(f"/api/mcp/master-resumes/{slug}/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data == FAKE_PDF
    disposition = pdf.headers.get("Content-Disposition") or ""
    assert disposition.startswith("inline;")
    assert "resume_go.pdf" in disposition

    pdf_download = v2_auth_client.get(f"/api/mcp/master-resumes/{slug}/pdf?download=1")
    assert pdf_download.status_code == 200
    download_disposition = pdf_download.headers.get("Content-Disposition") or ""
    assert download_disposition.startswith("attachment;")
    assert "resume_go.pdf" in download_disposition


def test_mcp_master_resume_render_api(v2_auth_client, monkeypatch):
    from relocation_jobs.mcp.render import CompileResult

    tex = r"""
\documentclass{article}
\begin{document}
Hello world
\end{document}
"""
    saved = v2_auth_client.put(
        "/api/mcp/master-resumes/java",
        json={"content": tex, "label": "Java backend"},
    )
    assert saved.status_code == 200
    slug = saved.get_json()["slug"]

    def fake_render(tex_path):
        pdf_path = tex_path.with_suffix(".pdf")
        pdf_path.write_bytes(FAKE_PDF)
        return CompileResult(ok=True, log="ok", pdf_path=str(pdf_path))

    monkeypatch.setattr("relocation_jobs.mcp.service.render.render_tex_to_pdf", fake_render)

    rendered = v2_auth_client.post(f"/api/mcp/master-resumes/{slug}/render")
    assert rendered.status_code == 200
    body = rendered.get_json()
    assert body["ok"] is True
    assert body["pdf_stored"] is True

    pdf = service.read_master_pdf_download(slug, user_id=1)
    assert pdf[0] == FAKE_PDF
    assert pdf[1] == "resume_java.pdf"


def test_mcp_project_master_round_trip(v2_auth_client):
    tex = r"""\subsection*{Relocation Jobs}
Built kuchup.com --- scrape, catalog, MCP CV pipeline.
"""
    saved = v2_auth_client.put(
        "/api/mcp/project-masters/relocation-jobs",
        json={"content": tex, "label": "Relocation Jobs (kuchup.com)"},
    )
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["ok"] is True
    assert body["slug"] == "relocation-jobs"
    assert body["label"] == "Relocation Jobs (kuchup.com)"

    listing = v2_auth_client.get("/api/mcp/project-masters")
    assert listing.status_code == 200
    items = listing.get_json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "relocation-jobs"
    assert items[0]["has_pdf"] is False
    assert items[0]["pdf_filename"] == "project_relocation_jobs.pdf"

    detail = v2_auth_client.get("/api/mcp/project-masters/relocation-jobs")
    assert detail.status_code == 200
    detail_body = detail.get_json()
    assert "kuchup.com" in detail_body["content"]
    assert detail_body["label"] == "Relocation Jobs (kuchup.com)"
    assert detail_body["has_pdf"] is False
    assert detail_body["pdf_filename"] == "project_relocation_jobs.pdf"


def test_mcp_project_master_pdf_round_trip(v2_auth_client):
    tex = r"""\subsection*{Relocation Jobs}
Built kuchup.com.
"""
    saved = v2_auth_client.put(
        "/api/mcp/project-masters/relocation-jobs",
        json={"content": tex, "label": "Relocation Jobs"},
    )
    assert saved.status_code == 200
    slug = saved.get_json()["slug"]
    mcp_repo.save_project_pdf(1, slug, FAKE_PDF)

    listing = v2_auth_client.get("/api/mcp/project-masters")
    item = next(i for i in listing.get_json()["items"] if i["slug"] == slug)
    assert item["has_pdf"] is True

    detail = v2_auth_client.get(f"/api/mcp/project-masters/{slug}")
    assert detail.get_json()["has_pdf"] is True

    pdf = v2_auth_client.get(f"/api/mcp/project-masters/{slug}/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data == FAKE_PDF


def test_mcp_project_master_render_api(v2_auth_client, monkeypatch):
    from relocation_jobs.mcp.render import CompileResult

    tex = r"""\subsection*{Relocation Jobs}
Built kuchup.com.
"""
    saved = v2_auth_client.put(
        "/api/mcp/project-masters/relocation-jobs",
        json={"content": tex, "label": "Relocation Jobs"},
    )
    assert saved.status_code == 200
    slug = saved.get_json()["slug"]

    def fake_render(tex_path):
        written = tex_path.read_text(encoding="utf-8")
        assert r"\documentclass" in written
        assert r"\subsection*{Relocation Jobs}" in written
        pdf_path = tex_path.with_suffix(".pdf")
        pdf_path.write_bytes(FAKE_PDF)
        return CompileResult(ok=True, log="ok", pdf_path=str(pdf_path))

    monkeypatch.setattr("relocation_jobs.mcp.service.render.render_tex_to_pdf", fake_render)

    rendered = v2_auth_client.post(f"/api/mcp/project-masters/{slug}/render")
    assert rendered.status_code == 200
    body = rendered.get_json()
    assert body["ok"] is True
    assert body["pdf_stored"] is True

    pdf = service.read_project_pdf_download(slug, user_id=1)
    assert pdf[0] == FAKE_PDF
    assert pdf[1] == "project_relocation_jobs.pdf"


def test_mcp_project_master_invalid_slug(v2_auth_client):
    resp = v2_auth_client.put(
        "/api/mcp/project-masters/!!!",
        json={"content": "x", "label": "Bad"},
    )
    assert resp.status_code == 400


def test_mcp_routes_require_auth(v2_client):
    assert v2_client.get("/api/mcp/profile").status_code == 401
    assert v2_client.get("/api/mcp/master-resumes").status_code == 401
    assert v2_client.get("/api/mcp/master-resumes/go/pdf").status_code == 401
    assert v2_client.post("/api/mcp/master-resumes/go/render").status_code == 401
    assert v2_client.get("/api/mcp/project-masters").status_code == 401
    assert v2_client.get("/api/mcp/project-masters/x").status_code == 401
    assert v2_client.get("/api/mcp/project-masters/x/pdf").status_code == 401
    assert v2_client.post("/api/mcp/project-masters/x/render").status_code == 401


def test_mcp_profile_isolated_per_user(v2_auth_client, auth_client):
    v2_auth_client.put(
        "/api/mcp/profile",
        json={"full_name": "Admin User", "email": "admin@example.com"},
    )

    register = auth_client.post(
        "/api/auth/register",
        json={"username": "otheruser", "password": "otherpass123"},
    )
    assert register.status_code == 200

    other = auth_client.get("/api/mcp/profile")
    assert other.status_code == 200
    assert other.get_json()["profile"]["full_name"] == ""


def test_apply_page_served(v2_client):
    resp = v2_client.get("/apply")
    assert resp.status_code == 200
    assert b"Application data" in resp.data


def test_company_workspace_page_served(v2_client):
    resp = v2_client.get("/company/uk/acme-backend-ltd")
    assert resp.status_code == 200
    assert b"Application workspace" in resp.data
