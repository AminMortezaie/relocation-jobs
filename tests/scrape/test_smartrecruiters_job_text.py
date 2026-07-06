from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.http_mock import MockResponse

from relocation_jobs.scrape.boards.smartrecruiters import (
    smartrecruiters_job_ad_html,
    smartrecruiters_posting_detail_url,
    smartrecruiters_posting_ids_from_url,
)
from relocation_jobs.scrape.descriptions import (
    format_job_description,
    needs_smartrecruiters_refetch,
    recover_smartrecruiters_plain_text,
)
from relocation_jobs.scrape.job_text import fetch_smartrecruiters_job_text

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "ats"
    / "smartrecruiters_posting_detail.json"
)
_JOB_URL = (
    "https://jobs.smartrecruiters.com/ScalableGmbH/"
    "744000128882669-ai-software-engineer-python-m-f-x-"
)


def test_smartrecruiters_posting_ids_from_url():
    assert smartrecruiters_posting_ids_from_url(_JOB_URL) == (
        "ScalableGmbH",
        "744000128882669",
    )
    assert smartrecruiters_posting_detail_url(_JOB_URL) == (
        "https://api.smartrecruiters.com/v1/companies/ScalableGmbH/postings/744000128882669"
    )


def test_smartrecruiters_job_ad_html_builds_sections():
    payload = json.loads(_FIXTURE.read_text())
    html = smartrecruiters_job_ad_html(payload)
    assert "<h3>Company Description</h3>" in html
    assert "<h3>Job Description</h3>" in html
    assert "Develop AI/LLM services" in html
    assert "<ul>" in html


def test_fetch_smartrecruiters_job_text_uses_api(monkeypatch):
    detail_url = smartrecruiters_posting_detail_url(_JOB_URL)
    payload = json.loads(_FIXTURE.read_text())

    def fake_get(url, *args, **kwargs):
        assert url == detail_url
        return MockResponse(json_data=payload)

    monkeypatch.setattr("relocation_jobs.scrape.job_text.requests.get", fake_get)
    result = __import__(
        "relocation_jobs.scrape.job_text",
        fromlist=["fetch_smartrecruiters_job_detail"],
    ).fetch_smartrecruiters_job_detail(_JOB_URL)
    assert "<h3>Job Description</h3>" in result.text
    assert "Python experience" in result.text
    assert result.location == "Munich, Germany"


def test_needs_smartrecruiters_refetch():
    clean = "<h3>Company Description</h3><p>Scalable Capital builds fintech products.</p>"
    assert needs_smartrecruiters_refetch("") is True
    assert needs_smartrecruiters_refetch(clean) is False
    assert needs_smartrecruiters_refetch("plain text without html sections") is True


def test_recover_smartrecruiters_plain_text_strips_page_chrome():
    noisy = (
        "scalable gmbh ai software engineer – python (m/f/x) | smartrecruiters "
        "google chrome microsoft edge apple safari mozilla firefox "
        "company description scalable capital is a leading digital investment platform. "
        "job description as an ai software engineer you will build scalable systems. "
        "qualifications several years of professional python experience. "
        "additional information international relocation support is provided. "
        "by clicking the link above privacy notice i'm interested share to wechat"
    )
    recovered = recover_smartrecruiters_plain_text(noisy)
    assert recovered is not None
    assert "<h3>Company Description</h3>" in recovered
    assert "scalable capital is a leading" in recovered.lower()
    assert "google chrome" not in recovered.lower()
    readable, display_html = format_job_description(noisy)
    assert "google chrome" not in readable.lower()
    assert "<h3>Job Description</h3>" in display_html
