"""Scrape_jobs coverage push — error paths, parsers, import fallbacks."""

from __future__ import annotations

import importlib
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from relocation_jobs import scrape_jobs as sj
from tests.helpers.http_mock import (
    MockResponse,
    install_requests_mock,
    json_response,
    load_ats_fixture,
    text_response,
)
from tests.helpers.playwright_mock import MockPlaywrightPage, install_playwright_mock


def _reload_scrape_without(module_name: str):
    real_import = __import__

    def block(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"blocked {module_name}")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=block):
        return importlib.reload(importlib.import_module("relocation_jobs.scrape_jobs"))


def test_scrape_import_error_httpx():
    mod = _reload_scrape_without("httpx")
    assert mod.HTTPX_AVAILABLE is False
    importlib.reload(importlib.import_module("relocation_jobs.scrape_jobs"))


def test_scrape_import_error_playwright():
    mod = _reload_scrape_without("playwright.sync_api")
    assert mod.PLAYWRIGHT_AVAILABLE is False
    importlib.reload(importlib.import_module("relocation_jobs.scrape_jobs"))


def test_smartrecruiters_location_text():
    assert sj._smartrecruiters_location_text(None) == ""
    assert sj._smartrecruiters_location_text({"fullLocation": "Berlin"}) == "Berlin"
    assert "Berlin" in sj._smartrecruiters_location_text({"city": "Berlin", "country": "DE"})


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Chief Technology Officer", False),
        ("Senior / Staff Product Engineer", True),
        ("Cloud Engineer Ops", False),
        ("AI Platform Specialist", False),
        ("Backend Software Engineer Marketing", True),
        ("Staff Engineer Platform", False),
    ],
)
def test_is_relevant_edge_cases(title, expected):
    assert sj.is_relevant(title) is expected


def test_title_from_listing_anchor_paths():
    from bs4 import BeautifulSoup

    html = """
    <div><a href="/jobs/1">Apply</a><span>Backend Engineer Platform Team</span></div>
    """
    soup = BeautifulSoup(html, "html.parser")
    a = soup.find("a")
    title = sj._title_from_listing_anchor(a)
    assert title

    html2 = '<a href="/jobs/2">View job</a>'
    a2 = BeautifulSoup(html2, "html.parser").find("a")
    assert sj._title_from_listing_anchor(a2)


def test_detect_ats_url_helpers():
    assert sj._detect_recruitee_from_careers_host("https://careers.acme.com/jobs")[0] == "recruitee"
    assert sj._detect_recruitee_from_careers_host("https://www.smartrecruiters.com/x")[0] is None
    assert sj._detect_recruitee_board_url("https://acme.recruitee.com/")[0] == "recruitee"
    assert sj._detect_recruitee_board_url("https://api.recruitee.com/")[0] is None
    assert sj._detect_teamtailor_from_url("https://acme.teamtailor.com/jobs")[0] == "teamtailor"
    assert sj._detect_workday_from_url("https://wd3.myworkdaysite.com/en-US/acme/careers")[0] == "workday"
    assert sj._detect_hirehive_from_url("https://acme.hirehive.com")[0] == "hirehive"


@pytest.mark.network
def test_scrape_greenhouse_bad_slug():
    assert sj.scrape_greenhouse("https://boards.greenhouse.io/embed/jobs") == []


@pytest.mark.network
def test_scrape_lever_and_greenhouse_errors(monkeypatch, capsys):
    install_requests_mock(
        monkeypatch,
        get_routes={
            "api.lever.co": MockResponse(status_code=500, text="err"),
            "boards-api.greenhouse.io": MockResponse(status_code=500, text="err"),
        },
    )
    assert sj.scrape_lever("https://jobs.lever.co/acme") == []
    assert sj.scrape_greenhouse("https://boards.greenhouse.io/acme") == []
    assert "error" in capsys.readouterr().out.lower()


@pytest.mark.network
def test_scrape_personio_xml_error_fallback(monkeypatch, capsys):
    install_requests_mock(
        monkeypatch,
        get_routes={"personio.de": MockResponse(status_code=500, text="fail")},
    )
    monkeypatch.setattr(
        sj,
        "scrape_personio_html",
        lambda *a, **k: [{"title": "Backend Engineer Platform", "url": "x"}],
    )
    jobs = sj.scrape_personio("https://acme.jobs.personio.de/", relevant_only=True)
    assert jobs


@pytest.mark.network
def test_bol_helpers():
    assert sj._bol_doelgroep_from_url("https://careers.bol.com/?doelgroep[]=tech")
    payload = sj._bol_search_payload("https://careers.bol.com/?doelgroep[]=tech")
    assert "body" in payload


@pytest.mark.network
def test_extract_helpers():
    assert sj._extract_lever("https://jobs.lever.co/acme")
    assert sj._extract_greenhouse("https://boards.greenhouse.io/acme")
    assert sj._extract_recruitee("https://acme.recruitee.com/")
    assert sj._extract_workable("https://apply.workable.com/acme/")
    assert sj._extract_ashby("https://jobs.ashbyhq.com/acme")


@pytest.mark.network
def test_scrape_teamtailor_html(monkeypatch):
    html = '<a href="/jobs/123-backend-engineer">Backend Engineer</a>'
    install_requests_mock(
        monkeypatch,
        get_routes={"teamtailor.com": text_response(html)},
    )
    monkeypatch.setattr(sj, "scrape_with_playwright", lambda *a, **k: [])
    jobs = sj.scrape_teamtailor("", "https://acme.teamtailor.com/jobs", relevant_only=True)
    assert isinstance(jobs, list)


@pytest.mark.network
def test_scrape_generic(monkeypatch):
    html = """
    <html><body>
      <a href="/careers/backend-engineer">Backend Engineer</a>
      <a href="/jobs/show_more">Show 5 more</a>
    </body></html>
    """
    install_requests_mock(
        monkeypatch,
        get_routes={"example.com": text_response(html)},
    )
    jobs = sj.scrape_generic("https://example.com/careers")
    assert isinstance(jobs, list)


@pytest.mark.network
def test_detect_ats_static_and_playwright(monkeypatch):
    page = MockPlaywrightPage(
        request_urls=[("https://api.lever.co/v0/postings/acme?mode=json", {})],
    )
    install_playwright_mock(monkeypatch, page=page)
    install_requests_mock(
        monkeypatch,
        get_routes={"example.com": text_response('<a href="https://jobs.lever.co/acme">Jobs</a>')},
    )
    sj.detect_ats_static("https://example.com/careers")
    sj.detect_ats_via_playwright("https://example.com/careers")


@pytest.mark.asyncio
async def test_get_jobs_async_playwright_fallback(monkeypatch):
    client = httpx.AsyncClient()
    monkeypatch.setattr(
        sj,
        "scrape_with_playwright",
        lambda url, **kw: [{"title": "Backend Engineer", "url": "https://example.com/j/1"}],
    )
    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
    company = {
        "name": "Co",
        "careers_url": "https://example.com/careers",
        "ats_type": "generic",
        "ats_url": "",
    }
    jobs = await sj.get_jobs_async(client, company, relevant_only=False)
    assert len(jobs) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_run_file_async_paths(monkeypatch, capsys):
    data = {
        "companies": [
            {
                "name": "Co",
                "city": "Berlin",
                "careers_url": "https://example.com/careers",
                "matching_jobs": [],
            }
        ]
    }
    monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
    monkeypatch.setattr(sj, "load_country", lambda k: data)
    monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
    monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)
    monkeypatch.setattr(sj, "get_jobs_async", AsyncMock(return_value=[]))
    await sj.run_file_async("test", skip_filled=False, concurrency=1)


def test_progress_and_cancel_reporters():
    sj.set_progress_reporter(lambda info: None)
    sj.set_cancel_checker(lambda: False)
    sj.set_review_reporter(lambda data: None)
    sj.clear_progress_reporter()
    sj.clear_cancel_checker()
    sj.clear_review_reporter()


@pytest.mark.network
def test_scrape_workday_helpers():
    sj._workday_api_and_base("https://wd3.myworkdaysite.com/wday/cxs/acme/site/jobs")


@pytest.mark.network
def test_scrape_module_main(monkeypatch):
    monkeypatch.setattr(sj, "HTTPX_AVAILABLE", False)
    monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py"])
    with pytest.raises(SystemExit):
        sj.main()


@pytest.mark.network
def test_scrape_rss_parser(monkeypatch):
    rss = """<?xml version="1.0"?><rss><channel><item><title>Backend Engineer</title><link>https://example.com/j/1</link></item></channel></rss>"""
    install_requests_mock(monkeypatch, get_routes={"example.com": text_response(rss)})
    jobs = sj.scrape_rss("https://example.com/feed.xml", relevant_only=True)
    assert isinstance(jobs, list)


def test_teamtailor_listing_empty():
    jobs = sj._teamtailor_listing_jobs_from_feed(
        [], [], "https://acme.teamtailor.com/jobs", relevant_only=True,
    )
    assert jobs == []


@pytest.mark.network
def test_get_jobs_sync_dispatch(monkeypatch):
    monkeypatch.setattr(sj, "scrape_lever", lambda url: [{"title": "Backend Engineer", "url": url}])
    company = {
        "name": "Co",
        "careers_url": "https://jobs.lever.co/acme",
        "ats_type": "lever",
        "ats_url": "https://jobs.lever.co/acme",
    }
    jobs = sj.get_jobs(company)
    assert jobs
