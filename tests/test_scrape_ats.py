"""ATS scrapers with mocked HTTP — no live network calls."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from relocation_jobs.scrape_jobs import scrape_greenhouse, scrape_lever

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.network
def test_scrape_greenhouse_filters_by_relevance(monkeypatch):
    payload = json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload

    monkeypatch.setattr(
        "relocation_jobs.scrape_jobs.requests.get",
        lambda *args, **kwargs: response,
    )

    jobs = scrape_greenhouse("https://boards.greenhouse.io/acmebackend")
    titles = [j["title"] for j in jobs]
    assert "Senior Backend Engineer" in titles
    assert "Marketing Manager" not in titles
    assert "Principal Software Engineer" not in titles  # excluded by keyword filter
    assert all(j.get("url") for j in jobs)


@pytest.mark.network
def test_scrape_lever_filters_cto(monkeypatch):
    payload = json.loads((FIXTURES / "lever_postings.json").read_text(encoding="utf-8"))
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload

    monkeypatch.setattr(
        "relocation_jobs.scrape_jobs.requests.get",
        lambda *args, **kwargs: response,
    )

    jobs = scrape_lever("https://jobs.lever.co/acme")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Backend Developer"
