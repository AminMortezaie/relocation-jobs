from __future__ import annotations

import os

from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.mcp import service
from relocation_jobs.mcp.types import ApplicationProfile

from tests.mcp.conftest import GO_MASTER_TEX, JAVA_MASTER_TEX

JOB_URL = "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456"


def test_get_job_context_includes_description(seeded_catalog_v2, mcp_documents):
    from relocation_jobs.catalog.repo import get_company, sync_company_board_to_catalog

    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    jobs = list(company["matching_jobs"])
    jobs[0]["description_text"] = "Senior backend role with distributed systems experience."
    company["matching_jobs"] = jobs
    sync_company_board_to_catalog("uk", company)

    os.environ["MCP_USERNAME"] = "admin"
    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        user_id=1,
    )
    assert ctx.has_description is True
    assert "distributed systems" in ctx.description_text


def test_get_job_context(seeded_catalog_v2, mcp_documents):
    os.environ["MCP_USERNAME"] = "admin"
    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        user_id=1,
    )
    assert ctx.company == "Acme Backend Ltd"
    assert ctx.title
    assert ctx.idempotency_key
    assert ctx.has_tailored_tex is False
    assert ctx.has_pdf is False
    assert ctx.has_cover_letter_tex is False
    assert ctx.has_cover_letter_pdf is False
    assert ctx.master_resume_slug == ""


def test_save_and_validate_tailored_tex(seeded_catalog_v2, mcp_documents):
    tailored = GO_MASTER_TEX.replace("Go Backend Engineer", "Senior Go Engineer")
    saved = service.save_tailored_tex_for_job(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        tailored,
        master_resume_slug="go",
        user_id=1,
    )
    assert saved["idempotency_key"]
    assert saved["master_resume_slug"] == "go"
    assert saved["overwritten"] is False

    validation = service.validate_tailored_tex(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        user_id=1,
    )
    assert validation.ok is True

    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        user_id=1,
    )
    assert ctx.has_tailored_tex is True
    assert ctx.master_resume_slug == "go"
    assert ctx.can_save_tailored_tex is True
    assert ctx.in_application_queue is False


def test_save_tailored_tex_overwrites_without_queue_membership(
    seeded_catalog_v2, mcp_documents,
):
    first = service.save_tailored_tex_for_job(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        GO_MASTER_TEX,
        master_resume_slug="go",
        user_id=1,
    )
    assert first["overwritten"] is False

    replacement = GO_MASTER_TEX.replace("Go Backend Engineer", "Staff Go Engineer")
    second = service.save_tailored_tex_for_job(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        replacement,
        master_resume_slug="go",
        user_id=1,
    )
    assert second["overwritten"] is True

    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        user_id=1,
    )
    assert ctx.can_save_tailored_tex is True
    assert ctx.in_application_queue is False
    assert ctx.has_tailored_tex is True

    tex = mcp_repo.read_tailored_tex(1, ctx.idempotency_key)
    assert "Staff Go Engineer" in tex


def test_save_cover_letter_tex_overwrites(seeded_catalog_v2, mcp_documents):
    first = service.save_cover_letter_tex_for_job(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        r"\documentclass{article}\begin{document}Hello\end{document}",
        user_id=1,
    )
    assert first["overwritten"] is False

    second = service.save_cover_letter_tex_for_job(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        r"\documentclass{article}\begin{document}Updated letter\end{document}",
        user_id=1,
    )
    assert second["overwritten"] is True

    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        user_id=1,
    )
    assert ctx.has_cover_letter_tex is True
    assert ctx.has_cover_letter_pdf is False
    assert ctx.cover_letter_pdf_filename.endswith("_cover_letter.pdf")

    tex = mcp_repo.read_cover_letter_tex(1, ctx.idempotency_key)
    assert "Updated letter" in tex


def test_validate_uses_correct_master_variant(seeded_catalog_v2, mcp_documents):
    tailored = JAVA_MASTER_TEX.replace("Java Backend Engineer", "Staff Java Engineer")
    service.save_tailored_tex_for_job(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        tailored,
        master_resume_slug="java",
        user_id=1,
    )
    ok = service.validate_tailored_tex(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        master_resume_slug="java",
        user_id=1,
    )
    assert ok.ok is True

    bad = service.validate_tailored_tex(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        master_resume_slug="go",
        user_id=1,
    )
    assert bad.ok is False


def test_list_master_resumes(seeded_catalog_v2, mcp_documents):
    items = service.list_master_resumes(user_id=1)
    slugs = {item.slug for item in items}
    assert slugs == {"go", "java"}
    labels = {item.slug: item.label for item in items}
    assert labels["go"] == "Go backend"


def test_list_application_queue_includes_looking_to_apply(
    v2_auth_client, seeded_catalog_v2, mcp_documents,
):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = board["companies"][0]
    job = co["jobs"][0]
    v2_auth_client.post(
        "/api/jobs/looking-to-apply",
        json={"country": "uk", "company": co["name"], "url": job["url"], "looking_to_apply": True},
    )

    items = service.list_application_queue(user_id=1, country="uk")
    assert any(item.url == job["url"] for item in items)


def test_list_looking_to_apply_jobs_excludes_pinned_only(
    v2_auth_client, seeded_catalog_v2, mcp_documents,
):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = board["companies"][0]
    first = co["jobs"][0]
    second = co["jobs"][1]
    v2_auth_client.post(
        "/api/jobs/looking-to-apply",
        json={"country": "uk", "company": co["name"], "url": first["url"], "looking_to_apply": True},
    )
    v2_auth_client.post(
        "/api/jobs/pin",
        json={"country": "uk", "company": co["name"], "url": second["url"], "pinned": True},
    )

    items = service.list_looking_to_apply_jobs(user_id=1, country="uk")
    urls = {item.url for item in items}
    assert first["url"] in urls
    assert second["url"] not in urls
    assert all(item.looking_to_apply for item in items)


def test_mark_job_applied(seeded_catalog_v2, mcp_documents):
    result = service.mark_job_applied(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        applied=True,
        user_id=1,
    )
    assert result["applied"] is True

    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        JOB_URL,
        user_id=1,
    )
    assert ctx.applied is True


def test_master_resume_and_profile_persist_in_db(db):
    mcp_repo.save_master_resume(1, "fullstack", GO_MASTER_TEX, label="Full stack")
    mcp_repo.save_profile(
        1,
        ApplicationProfile(
            full_name="Ada",
            email="ada@example.com",
            pipeline=["Focus on backend roles.", "Use concise bullet points."],
        ),
    )
    assert "Example Corp" in mcp_repo.read_master_resume(1, "fullstack")
    profile = mcp_repo.read_profile(1)
    assert profile.full_name == "Ada"
    assert profile.email == "ada@example.com"
    assert profile.pipeline == ["Focus on backend roles.", "Use concise bullet points."]


def test_wrap_project_fragment_for_pdf():
    wrapped = service.wrap_project_fragment_for_pdf(r"\subsection*{Demo}")
    assert r"\documentclass" in wrapped
    assert r"\subsection*{Demo}" in wrapped
    assert wrapped.rstrip().endswith(r"\end{document}")

    full = r"\documentclass{article}\begin{document}Hi\end{document}"
    assert service.wrap_project_fragment_for_pdf(full) == full


def test_project_master_round_trip(db):
    saved = mcp_repo.save_project_master(
        1,
        "Relocation Jobs!",
        r"\subsection*{Relocation Jobs}" "\nVisa job board at kuchup.com.",
        label="Relocation Jobs (kuchup.com)",
    )
    assert saved["slug"] == "relocation-jobs"
    assert saved["label"] == "Relocation Jobs (kuchup.com)"

    items = service.list_project_masters(user_id=1)
    assert {item.slug for item in items} == {"relocation-jobs"}
    assert items[0].label == "Relocation Jobs (kuchup.com)"

    detail = service.get_project_master_detail("relocation-jobs", user_id=1)
    assert "kuchup.com" in detail["content"]
    assert detail["slug"] == "relocation-jobs"

    body = mcp_repo.read_project_master(1, "relocation-jobs")
    assert "Visa job board" in body
    assert r"\subsection*" in body


def test_project_master_invalid_slug(db):
    try:
        mcp_repo.save_project_master(1, "", "content")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "required" in str(exc)
