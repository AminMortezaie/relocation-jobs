"""Tests for get_jobs() ATS dispatch with cached company configs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from relocation_jobs import scrape_jobs as sj
from tests.helpers.http_mock import install_requests_mock, json_response, load_ats_fixture, text_response


ATS_CASES = [
    ("greenhouse", "https://boards.greenhouse.io/acme", "scrape_greenhouse"),
    ("lever", "https://jobs.lever.co/acme", "scrape_lever"),
    ("lever_eu", "https://jobs.eu.lever.co/acme", "scrape_lever"),
    ("greenhouse_eu", "https://boards.eu.greenhouse.io/acme", "scrape_greenhouse"),
    ("ashby", "https://jobs.ashbyhq.com/acme", "scrape_ashby"),
    ("workable", "https://apply.workable.com/acme/", "scrape_workable"),
    ("recruitee", "https://acme.recruitee.com/", "scrape_recruitee"),
    ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/Acme/postings", "scrape_smartrecruiters"),
    ("workday", "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|https://acme.wd3.myworkdayjobs.com/en-US/careers", "scrape_workday"),
    ("bamboohr", "https://acme.bamboohr.com/careers/list", "scrape_bamboohr"),
    ("hirehive", "https://acme.hirehive.com", "scrape_hirehive"),
    ("epam", "https://careers.epam.com/", "scrape_epam"),
    ("rss", "https://example.com/feed.xml", "scrape_rss"),
    ("deel", "https://jobs.deel.com/acme", "scrape_deel"),
    ("join", "https://join.com/companies/acme", "scrape_join"),
    ("applytojob", "https://acme.applytojob.com/", "scrape_applytojob"),
    ("movingimage", "https://www.movingimage.com/careers", "scrape_movingimage"),
    ("project_a", "https://www.project-a.vc/careers", "scrape_project_a"),
    ("bol", "https://careers.bol.com/en/jobs/", "scrape_bol"),
    ("job_shop", "https://careers.acme.example.com/", "scrape_job_shop"),
    ("jibe", "https://jobs.booking.com/booking/jobs", "scrape_jibe"),
    ("atlassian", "https://www.atlassian.com/company/careers/all-jobs", "scrape_atlassian"),
]


@pytest.mark.parametrize("ats_type,ats_url,scraper_name", ATS_CASES)
def test_get_jobs_dispatches_to_scraper(monkeypatch, ats_type, ats_url, scraper_name):
    sample_jobs = [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]
    mock_scraper = MagicMock(return_value=sample_jobs)
    monkeypatch.setattr(sj, scraper_name, mock_scraper)

    company = {
        "name": "TestCo",
        "careers_url": ats_url,
        "ats_type": ats_type,
        "ats_url": ats_url,
    }
    jobs = sj.get_jobs(company)
    assert jobs == sample_jobs
    mock_scraper.assert_called_once()


def test_get_jobs_no_careers_url_returns_empty():
    assert sj.get_jobs({"name": "Empty", "careers_url": ""}) == []


def test_get_jobs_teamtailor_passes_careers_url(monkeypatch):
    mock_scraper = MagicMock(return_value=[])
    monkeypatch.setattr(sj, "scrape_teamtailor", mock_scraper)
    careers = "https://acme.teamtailor.com/jobs"
    company = {
        "name": "TestCo",
        "careers_url": careers,
        "ats_type": "teamtailor",
        "ats_url": "api-key-123",
    }
    sj.get_jobs(company)
    mock_scraper.assert_called_once_with("api-key-123", careers)


def test_get_jobs_generic_fallback(monkeypatch):
    monkeypatch.setattr(sj, "scrape_generic", MagicMock(return_value=[]))
    monkeypatch.setattr(sj, "scrape_with_playwright", MagicMock(return_value=[]))
    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)

    company = {
        "name": "GenericCo",
        "careers_url": "https://example.com/careers",
        "ats_type": "generic",
        "ats_url": "",
    }
    jobs = sj.get_jobs(company)
    assert jobs == []
    sj.scrape_generic.assert_called_once()
    sj.scrape_with_playwright.assert_called_once()


def test_get_jobs_auto_detects_static(monkeypatch):
    payload = {
        "jobs": [
            {
                "title": "Backend Engineer",
                "absolute_url": "https://example.com/j/1",
                "location": {"name": "Berlin"},
            }
        ]
    }
    install_requests_mock(
        monkeypatch,
        get_routes={
            "example.com/careers": text_response("https://boards.greenhouse.io/acme"),
            "boards-api.greenhouse.io": json_response(payload),
        },
    )
    company = {
        "name": "DetectCo",
        "careers_url": "https://example.com/careers",
    }
    jobs = sj.get_jobs(company)
    assert company.get("ats_type") == "greenhouse"
    assert any("Backend" in j["title"] for j in jobs)


def test_apply_known_ats_override(monkeypatch):
    mock_scraper = MagicMock(return_value=[])
    monkeypatch.setattr(sj, "scrape_bol", mock_scraper)
    company = {
        "name": "bol",
        "careers_url": "https://careers.bol.com/en/jobs/",
        "ats_type": "generic",
        "ats_url": "",
    }
    sj.get_jobs(company)
    assert company["ats_type"] == "bol"
    mock_scraper.assert_called_once()
