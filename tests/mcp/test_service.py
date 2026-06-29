from __future__ import annotations

import os

import pytest

from relocation_jobs.mcp import paths
from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.mcp import service


@pytest.fixture
def mcp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PANEL_DATA_DIR", str(tmp_path))
    paths.ensure_data_layout()
    return tmp_path


def test_get_job_context(seeded_catalog_v2, mcp_data_dir):
    os.environ["MCP_USERNAME"] = "admin"
    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456",
        user_id=1,
    )
    assert ctx.company == "Acme Backend Ltd"
    assert ctx.title
    assert ctx.idempotency_key
    assert ctx.application_dir.endswith(ctx.idempotency_key)


def test_save_and_validate_tailored_tex(seeded_catalog_v2, mcp_data_dir):
    master = mcp_repo.read_master_resume()
    tailored = master.replace("Backend Software Engineer", "Backend Engineer (Go)")
    saved = service.save_tailored_tex_for_job(
        "uk",
        "Acme Backend Ltd",
        "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456",
        tailored,
        user_id=1,
    )
    assert saved["path"].endswith("resume.tex")

    validation = service.validate_tailored_tex(
        "uk",
        "Acme Backend Ltd",
        "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456",
        user_id=1,
    )
    assert validation.ok is True


def test_list_application_queue_includes_looking_to_apply(v2_auth_client, seeded_catalog_v2, mcp_data_dir):
    board = v2_auth_client.get("/api/board?country=uk").get_json()
    co = board["companies"][0]
    job = co["jobs"][0]
    v2_auth_client.post(
        "/api/jobs/looking-to-apply",
        json={"country": "uk", "company": co["name"], "url": job["url"], "looking_to_apply": True},
    )

    items = service.list_application_queue(user_id=1, country="uk")
    assert any(item.url == job["url"] for item in items)


def test_mark_job_applied(seeded_catalog_v2, mcp_data_dir):
    result = service.mark_job_applied(
        "uk",
        "Acme Backend Ltd",
        "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456",
        applied=True,
        user_id=1,
    )
    assert result["applied"] is True

    ctx = service.get_job_context(
        "uk",
        "Acme Backend Ltd",
        "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456",
        user_id=1,
    )
    assert ctx.applied is True
