from __future__ import annotations

import pytest

from relocation_jobs.catalog.repo import get_company
from relocation_jobs.core.job_identity import normalize_job_url
from relocation_jobs.mcp import service
from tests.mcp.test_add_company import _patch_company_enrichment


LINKEDIN_URL = "https://www.linkedin.com/jobs/view/1234567890"
SAMPLE_JD = (
    "We are hiring a Senior Backend Engineer to build scalable APIs with Go, "
    "Kubernetes, and PostgreSQL. You will own services end to end."
)
POSTED_AT = "2025-06-15"


def _seed_company(db, monkeypatch, *, suffix: str):
    _patch_company_enrichment(monkeypatch)
    name = f"BrightPattern MCP Co {suffix}"
    service.add_company(
        name,
        f"https://boards.greenhouse.io/brightpattern-mcp-{suffix}",
        country="uk",
    )
    return name


def test_add_position_inserts_role(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="insert")
    result = service.add_position(
        "uk",
        company,
        "Senior Backend Engineer",
        LINKEDIN_URL,
        location="London, UK",
        description_text=SAMPLE_JD,
        posted_at=POSTED_AT,
    )
    assert result.added == 1
    assert result.already_existed is False
    assert result.company == company
    assert result.title == "Senior Backend Engineer"
    assert result.location == "London, UK"
    assert result.has_description is True
    assert result.posted_at == POSTED_AT
    assert result.idempotency_key
    assert result.url == normalize_job_url(LINKEDIN_URL)

    stored = get_company("uk", company)
    assert stored is not None
    urls = {job.get("url") for job in stored.get("matching_jobs") or []}
    assert normalize_job_url(LINKEDIN_URL) in urls


def test_add_position_idempotent(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="idem")
    linkedin_url = "https://www.linkedin.com/jobs/view/9999999991"
    first = service.add_position(
        "uk",
        company,
        "Platform Engineer",
        linkedin_url,
        description_text=SAMPLE_JD,
        posted_at=POSTED_AT,
    )
    second = service.add_position(
        "uk",
        company,
        "Platform Engineer",
        linkedin_url,
        description_text=SAMPLE_JD,
        posted_at=POSTED_AT,
    )
    assert first.added == 1
    assert second.added == 0
    assert second.already_existed is True
    assert second.idempotency_key == first.idempotency_key


def test_add_position_backfills_description_on_duplicate(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="desc")
    linkedin_url = "https://www.linkedin.com/jobs/view/9999999992"
    service.add_position(
        "uk", company, "SRE", linkedin_url,
        description_text=SAMPLE_JD, posted_at=POSTED_AT,
    )
    extra = "On-call rotation and observability for a multi-tenant SaaS platform with strict SLOs."
    result = service.add_position(
        "uk",
        company,
        "SRE",
        linkedin_url,
        description_text=extra,
        posted_at=POSTED_AT,
    )
    assert result.description_saved is True
    assert result.has_description is True
    ctx = service.get_job_context("uk", company, linkedin_url)
    assert "observability" in ctx.description_text


def test_add_position_requires_linkedin_posted_at(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="linkedin-ts")
    with pytest.raises(ValueError, match="posted_at is required"):
        service.add_position(
            "uk",
            company,
            "Engineer",
            "https://www.linkedin.com/jobs/view/8888888887",
            description_text=SAMPLE_JD,
        )


def test_add_position_requires_linkedin_jd(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="linkedin-jd")
    with pytest.raises(ValueError, match="description_text is required"):
        service.add_position(
            "uk",
            company,
            "Engineer",
            "https://www.linkedin.com/jobs/view/8888888888",
        )


def test_save_position_description_appends(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="save-desc")
    linkedin_url = "https://www.linkedin.com/jobs/view/7777777777"
    jd = "A" * 80
    extra = "B" * 80
    service.add_position(
        "uk", company, "Engineer", linkedin_url,
        description_text=jd, posted_at=POSTED_AT,
    )
    result = service.save_position_description(
        "uk",
        company,
        linkedin_url,
        description_text=extra,
    )
    assert result.description_saved is True
    assert result.appended is True
    ctx = service.get_job_context("uk", company, linkedin_url)
    assert jd in ctx.description_text
    assert extra in ctx.description_text


def test_add_position_requires_existing_company(db):
    with pytest.raises(LookupError, match="Company not found"):
        service.add_position(
            "uk",
            "missing-co",
            "Engineer",
            LINKEDIN_URL,
            description_text=SAMPLE_JD,
            posted_at=POSTED_AT,
        )


def test_add_position_validates_inputs():
    with pytest.raises(ValueError, match="title is required"):
        service.add_position("uk", "Acme", "", LINKEDIN_URL)
    with pytest.raises(ValueError, match="url is required"):
        service.add_position("uk", "Acme", "Engineer", "")
