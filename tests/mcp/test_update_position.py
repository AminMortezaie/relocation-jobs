from __future__ import annotations

from relocation_jobs.mcp import service
from tests.mcp.test_add_position import POSTED_AT, SAMPLE_JD, _seed_company


def test_update_position_overwrites_description(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="upd-desc")
    linkedin_url = "https://www.linkedin.com/jobs/view/5555555551"
    service.add_position("uk", company, "Engineer", linkedin_url, description_text=SAMPLE_JD, posted_at=POSTED_AT)
    result = service.update_position(
        "uk",
        company,
        linkedin_url,
        description_text="Corrected job description with enough characters to pass validation comfortably.",
    )
    assert "description_text" in result.updated_fields
    ctx = service.get_job_context("uk", company, linkedin_url)
    assert "Corrected job description" in ctx.description_text
    assert "Kubernetes" not in ctx.description_text


def test_save_position_description_overwrite(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="save-ow")
    linkedin_url = "https://www.linkedin.com/jobs/view/5555555552"
    service.add_position("uk", company, "Engineer", linkedin_url, description_text=SAMPLE_JD, posted_at=POSTED_AT)
    result = service.save_position_description(
        "uk",
        company,
        linkedin_url,
        "Replacement JD text that is long enough for overwrite mode to store in catalog.",
        overwrite=True,
    )
    assert result.overwritten is True
    ctx = service.get_job_context("uk", company, linkedin_url)
    assert "Replacement JD" in ctx.description_text


def test_update_position_title_and_location(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="upd-meta")
    linkedin_url = "https://www.linkedin.com/jobs/view/5555555553"
    service.add_position(
        "uk",
        company,
        "Old Title",
        linkedin_url,
        description_text=SAMPLE_JD,
        location="Berlin",
        posted_at=POSTED_AT,
    )
    result = service.update_position(
        "uk",
        company,
        linkedin_url,
        title="Senior Engineer",
        location="London, UK",
    )
    assert set(result.updated_fields) == {"title", "location"}
    assert result.title == "Senior Engineer"
    assert result.location == "London, UK"


def test_update_position_posted_at(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="upd-ts")
    linkedin_url = "https://www.linkedin.com/jobs/view/5555555555"
    service.add_position(
        "uk", company, "Engineer", linkedin_url,
        description_text=SAMPLE_JD, posted_at="2025-01-01",
    )
    result = service.update_position(
        "uk", company, linkedin_url, posted_at="2025-06-20",
    )
    assert "posted_at" in result.updated_fields
    assert result.posted_at == "2025-06-20"
    ctx = service.get_job_context("uk", company, linkedin_url)
    assert ctx.posted_at == "2025-06-20"


def test_update_position_clear_description(db, monkeypatch):
    company = _seed_company(db, monkeypatch, suffix="clr-desc")
    linkedin_url = "https://www.linkedin.com/jobs/view/5555555554"
    service.add_position("uk", company, "Engineer", linkedin_url, description_text=SAMPLE_JD, posted_at=POSTED_AT)
    result = service.update_position(
        "uk",
        company,
        linkedin_url,
        clear_description=True,
    )
    assert result.has_description is False
    ctx = service.get_job_context("uk", company, linkedin_url)
    assert ctx.has_description is False
