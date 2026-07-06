from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.http_mock import MockResponse

from relocation_jobs.scrape.boards.ashby import (
    ashby_job_content,
    ashby_job_ids_from_url,
)
from relocation_jobs.scrape.descriptions import format_job_description, needs_ashby_refetch
from relocation_jobs.scrape.job_text import fetch_ashby_job_text

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ats" / "ashby.json"
_JOB_URL = "https://jobs.ashbyhq.com/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_API_URL = "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensationRanges=true"


def test_ashby_job_ids_from_url():
    assert ashby_job_ids_from_url(_JOB_URL) == (
        "acme",
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )


def test_fetch_ashby_job_text_returns_html(monkeypatch):
    payload = json.loads(_FIXTURE.read_text())

    def fake_get(url, *args, **kwargs):
        assert url == _API_URL
        return MockResponse(json_data=payload)

    monkeypatch.setattr("relocation_jobs.scrape.boards.ashby.requests.get", fake_get)
    result = __import__(
        "relocation_jobs.scrape.job_text",
        fromlist=["fetch_ashby_job_detail"],
    ).fetch_ashby_job_detail(_JOB_URL)
    assert "<p>" in result.text
    assert "visa sponsorship" in result.text
    assert result.location == "Berlin, Germany"


def test_ashby_job_content_picks_matching_posting(monkeypatch):
    payload = json.loads(_FIXTURE.read_text())

    def fake_get(url, *args, **kwargs):
        return MockResponse(json_data=payload)

    monkeypatch.setattr("relocation_jobs.scrape.boards.ashby.requests.get", fake_get)
    assert "visa sponsorship" in ashby_job_content("acme", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert ashby_job_content("acme", "missing-id") == ""


def test_needs_ashby_refetch():
    plain = "adjoe builds the technologies behind mobile apps growth and monetization."
    assert needs_ashby_refetch("") is True
    assert needs_ashby_refetch(plain) is True
    assert needs_ashby_refetch("<p>Build backend services with <strong>Go</strong>.</p>") is False
