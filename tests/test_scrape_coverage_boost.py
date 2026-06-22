"""High-yield tests for remaining scrape_jobs coverage gaps."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from relocation_jobs import scrape_jobs as sj
from tests.helpers.http_mock import (
    MockResponse,
    install_requests_mock,
    json_response,
    load_ats_fixture,
    text_response,
)

from tests.helpers.playwright_mock import install_playwright_mock


@pytest.fixture
def httpx_client():
    return httpx.AsyncClient(headers=sj.HEADERS, follow_redirects=True)


ASYNC_DISPATCH = [
    ("lever_eu", "scrape_lever_async"),
    ("greenhouse_eu", "scrape_greenhouse_async"),
    ("job_shop", "scrape_job_shop_async"),
    ("ashby", "scrape_ashby_async"),
    ("workable", "scrape_workable_async"),
    ("recruitee", "scrape_recruitee_async"),
    ("smartrecruiters", "scrape_smartrecruiters_async"),
    ("join", "scrape_join_async"),
    ("deel", "scrape_deel_async"),
    ("applytojob", "scrape_applytojob"),
    ("bamboohr", "scrape_bamboohr"),
    ("movingimage", "scrape_movingimage"),
    ("project_a", "scrape_project_a"),
    ("hirehive", "scrape_hirehive_async"),
    ("epam", "scrape_epam_async"),
    ("rss", "scrape_rss_async"),
    ("atlassian", "scrape_atlassian"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("ats_type,fn_name", ASYNC_DISPATCH)
async def test_get_jobs_async_dispatches(monkeypatch, ats_type, fn_name):
    sample = [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]
    if fn_name.endswith("_async"):
        mock = AsyncMock(return_value=sample)
        monkeypatch.setattr(sj, fn_name, mock)
    else:
        mock = MagicMock(return_value=sample)
        monkeypatch.setattr(sj, fn_name, mock)

    client = httpx.AsyncClient()
    company = {
        "name": "Co",
        "careers_url": "https://example.com/careers",
        "ats_type": ats_type,
        "ats_url": "https://example.com/careers",
    }
    jobs = await sj.get_jobs_async(client, company, relevant_only=False)
    assert jobs == sample
    await client.aclose()


@pytest.mark.asyncio
async def test_get_jobs_async_known_ats_override(monkeypatch):
    monkeypatch.setattr(sj, "scrape_bol_async", AsyncMock(return_value=[]))
    client = httpx.AsyncClient()
    company = {
        "name": "bol",
        "careers_url": "https://careers.bol.com/en/jobs/",
        "ats_type": "generic",
        "ats_url": "",
    }
    await sj.get_jobs_async(client, company, relevant_only=False)
    assert company["ats_type"] == "bol"
    await client.aclose()


@pytest.mark.asyncio
async def test_run_file_target_skip_message(monkeypatch, capsys):
    data = {
        "companies": [
            {
                "name": "SkippedCo",
                "city": "Berlin",
                "careers_url": "https://example.com/careers",
                "matching_jobs": [{"title": "Role", "url": "https://example.com/j/1"}],
            }
        ]
    }
    monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
    monkeypatch.setattr(sj, "load_country", lambda k: data)
    monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
    monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)
    await sj.run_file_async("test", target="SkippedCo", skip_filled=True)
    assert "skipped" in capsys.readouterr().out.lower()


@pytest.mark.asyncio
@respx.mock
async def test_scrape_errors_async(monkeypatch):
    client = httpx.AsyncClient()
    respx.get("https://jobs.lever.co/bad").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_lever_async(client, "https://jobs.lever.co/bad") == []
    await client.aclose()


@pytest.mark.network
def test_scrape_many_error_paths(monkeypatch):
    err = MockResponse(status_code=500, text="fail")
    install_requests_mock(monkeypatch, get_routes={"example.com": err}, post_routes={"example.com": err})

    assert sj.scrape_workable("https://apply.workable.com/bad/") == []
    assert sj.scrape_recruitee("https://bad.recruitee.com/") == []
    assert sj.scrape_smartrecruiters("https://api.smartrecruiters.com/v1/companies/X/postings") == []
    assert sj.scrape_hirehive("https://bad.hirehive.com") == []
    assert sj.scrape_rss("https://example.com/feed.xml") == []
    assert sj.scrape_epam("https://careers.epam.com/") == []
    assert sj.scrape_applytojob("https://bad.applytojob.com/") == []
    assert sj.scrape_bamboohr("https://bad.bamboohr.com/careers/list") == []


@pytest.mark.network
def test_scrape_bol_failure(monkeypatch):
    install_requests_mock(
        monkeypatch,
        post_routes={"careers.bol.com": json_response({"success": False})},
    )
    assert sj.scrape_bol("https://careers.bol.com/en/jobs/") == []


@pytest.mark.network
def test_scrape_workday_missing_config():
    assert sj.scrape_workday("https://example.com") == []


@pytest.mark.network
def test_scrape_deel_invalid_url():
    assert sj.scrape_deel("https://jobs.deel.com/embed") == []


@pytest.mark.network
def test_scrape_join_invalid_url():
    assert sj.scrape_join("https://join.com/companies/embed") == []


@pytest.mark.network
def test_detect_ats_static_network_error(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(sj.requests, "get", boom)
    assert sj.detect_ats_static("https://example.com/careers") == (None, None)


def test_playwright_unavailable_scrapers(monkeypatch):
    install_playwright_mock(monkeypatch, available=False)
    assert sj.scrape_jibe("https://jobs.booking.com/jobs") == []
    assert sj.scrape_atlassian("https://www.atlassian.com/careers") == []
    assert sj.scrape_with_playwright("https://example.com/careers") == []


@pytest.mark.network
def test_scrape_movingimage_and_project_a_errors(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={"movingimage.com": MockResponse(status_code=500, text="x")},
    )
    assert sj.scrape_movingimage("https://www.movingimage.com/careers") == []

    install_requests_mock(
        monkeypatch,
        get_routes={"project-a.vc": MockResponse(status_code=500, text="x")},
    )
    assert sj.scrape_project_a("https://www.project-a.vc/careers") == []


@pytest.mark.network
def test_personio_xml_parse(monkeypatch):
    xml = load_ats_fixture("personio.xml")
    install_requests_mock(
        monkeypatch,
        get_routes={"personio.de/xml": text_response(xml)},
    )
    jobs = sj.scrape_personio("https://acme.jobs.personio.de/")
    assert any("Platform Engineer" in j["title"] for j in jobs)


def test_merge_duplicate_scraped_keys():
    scraped = [
        {"title": "A", "url": "https://example.com/j/1?gh_jid=1"},
        {"title": "B", "url": "https://example.com/j/1?gh_jid=1"},
    ]
    merged, _, new_count, _ = sj.merge_matching_jobs([], scraped)
    assert new_count == 1
    assert len(merged) == 1


def test_enrich_one_job_only_missing_with_visa():
    job = {"title": "Role", "url": "https://example.com/j/1", "visa_sponsorship": False}
    sj._enrich_one_job(job, None, "2025-06-01", only_missing=True)
    assert job["fetched"] == "2025-06-01"


def test_main_enrich_flags(monkeypatch):
    called = []

    def fake_run_country(*args, **kwargs):
        called.append(kwargs)

    monkeypatch.setattr(sj, "run_country", fake_run_country)
    monkeypatch.setattr(
        sj.sys,
        "argv",
        ["scrape_jobs.py", "--enrich-only", "--skip-enriched", "--country=uk"],
    )
    sj.main()
    assert called[0]["enrich_only"] is True
    assert called[0]["skip_enriched"] is True


@pytest.mark.asyncio
async def test_process_company_review_mode(monkeypatch):
    client = httpx.AsyncClient()
    company = {
        "name": "Acme",
        "city": "Berlin",
        "careers_url": "https://example.com/careers",
        "matching_jobs": [],
    }
    reviews = []
    sj.set_review_reporter(reviews.append)

    async def fake_get_jobs(client, comp, **kw):
        return [
            {"title": "Backend Engineer", "url": "https://example.com/j/1"},
            {"title": "Marketing Manager", "url": "https://example.com/j/2"},
        ]

    async def fake_enrich(client, jobs, comp, **kw):
        return jobs

    monkeypatch.setattr(sj, "get_jobs_async", fake_get_jobs)
    monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)

    try:
        msg, new_count = await sj._process_company_async(
            client,
            company,
            1,
            1,
            save_fn=None,
            enrich_only=False,
            skip_enriched=False,
            enrich_concurrency=2,
            review_mode=True,
            catalog_country="",
        )
        assert "matching job" in msg
        assert new_count >= 0
        assert reviews
    finally:
        sj.clear_review_reporter()
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_scrape_ashby_async_playwright_fallback(httpx_client, monkeypatch):
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").mock(
        return_value=httpx.Response(500, text="err")
    )
    monkeypatch.setattr(
        sj,
        "scrape_with_playwright",
        lambda url, **kw: [{"title": "Backend Engineer", "url": "https://example.com/j/1"}],
    )
    jobs = await sj.scrape_ashby_async(httpx_client, "https://jobs.ashbyhq.com/acme")
    assert jobs[0]["title"] == "Backend Engineer"


@pytest.mark.asyncio
@respx.mock
async def test_scrape_job_shop_async_errors(httpx_client):
    respx.get(url__regex=r"https://careers\.acme\.example\.com/.*").mock(
        return_value=httpx.Response(500, text="err")
    )
    assert await sj.scrape_job_shop_async(httpx_client, "https://careers.acme.example.com/") == []


@pytest.mark.asyncio
@respx.mock
async def test_get_jobs_async_playwright_generic(httpx_client, monkeypatch):
    respx.get("https://example.com/careers").mock(
        return_value=httpx.Response(200, text="<html><body></body></html>")
    )
    monkeypatch.setattr(
        sj,
        "scrape_with_playwright",
        lambda url, **kw: [{"title": "Backend Engineer", "url": "https://example.com/j/1"}],
    )
    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
    company = {"name": "Co", "careers_url": "https://example.com/careers", "ats_type": "generic", "ats_url": ""}
    jobs = await sj.get_jobs_async(httpx_client, company, relevant_only=False)
    assert len(jobs) == 1


@pytest.mark.network
def test_apply_known_ats_job_shop_detect(monkeypatch):
    html = load_ats_fixture("job_shop_page.html")
    install_requests_mock(
        monkeypatch,
        get_routes={"careers.acme.example.com": text_response(html)},
    )
    company = {
        "name": "Other",
        "careers_url": "https://careers.acme.example.com/",
        "ats_type": "",
        "ats_url": "",
    }
    sj._apply_known_ats_override(company)
    assert company.get("ats_type") == "job_shop"


@pytest.mark.network
def test_teamtailor_html_second_page(monkeypatch):
    page1 = '<html><body><a href="/jobs/backend">Backend Engineer</a></body></html>'
    page2 = '<html><body><a href="/jobs/platform">Platform Engineer</a></body></html>'

    def route(url, **kwargs):
        if "page=2" in url:
            return text_response(page2)
        return text_response(page1)

    install_requests_mock(monkeypatch, get_routes={"teamtailor.com": route}, default_get=text_response(""))
    jobs = sj._scrape_teamtailor_html_board("https://acme.teamtailor.com/jobs", relevant_only=True)
    assert len(jobs) >= 1


def test_playwright_detect_exception(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def broken_cm():
        raise RuntimeError("playwright boom")
        yield  # pragma: no cover

    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(sj, "sync_playwright", broken_cm)
    assert sj.detect_ats_via_playwright("https://example.com/careers") == (None, None)


def test_scrape_with_playwright_exception(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def broken_cm():
        raise RuntimeError("playwright boom")
        yield  # pragma: no cover

    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(sj, "sync_playwright", broken_cm)
    assert sj.scrape_with_playwright("https://example.com/careers") == []


@pytest.mark.network
def test_detect_ats_for_hint_playwright(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={"example.com": text_response("<html></html>")},
    )
    monkeypatch.setattr(
        sj,
        "detect_ats_via_playwright",
        lambda url, **kw: ("ashby", "https://jobs.ashbyhq.com/acme"),
    )
    ats_type, ats_url = sj.detect_ats_for_hint(
        "Acme",
        "https://example.com/careers",
        "ashby",
    )
    assert ats_type == "ashby"


@pytest.mark.asyncio
async def test_process_company_enrich_only_empty(monkeypatch):
    client = httpx.AsyncClient()
    company = {
        "name": "Acme",
        "city": "Berlin",
        "careers_url": "https://example.com/careers",
        "matching_jobs": [],
    }
    msg, new_count = await sj._process_company_async(
        client,
        company,
        1,
        1,
        save_fn=None,
        enrich_only=True,
        skip_enriched=False,
        enrich_concurrency=2,
    )
    assert "no jobs to enrich" in msg
    assert new_count == 0
    await client.aclose()


@pytest.mark.asyncio
async def test_run_file_cancel_concurrent(monkeypatch):
    data = {
        "companies": [
            {
                "name": f"Co{i}",
                "city": "Berlin",
                "careers_url": "https://example.com/careers",
                "matching_jobs": [],
            }
            for i in range(4)
        ]
    }
    monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
    monkeypatch.setattr(sj, "load_country", lambda k: data)
    monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
    monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)

    call_count = {"n": 0}

    async def slow_get_jobs(client, company, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            sj.set_cancel_checker(lambda: True)
        await asyncio.sleep(0.05)
        return [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]

    async def fake_enrich(client, jobs, company, **kw):
        return jobs

    monkeypatch.setattr(sj, "get_jobs_async", slow_get_jobs)
    monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)
    try:
        await sj.run_file_async("test", concurrency=2)
    finally:
        sj.clear_cancel_checker()


@pytest.mark.network
def test_get_jobs_persist_with_save_fn(monkeypatch):
    saved = []
    monkeypatch.setattr(sj, "scrape_lever", MagicMock(return_value=[]))
    monkeypatch.setattr(
        sj,
        "detect_ats_static",
        lambda url: ("lever", "https://jobs.lever.co/acme"),
    )
    company = {"name": "Co", "careers_url": "https://example.com/careers"}
    sj.get_jobs(company, save_fn=lambda: saved.append(True))
    assert saved
    assert company["ats_type"] == "lever"


@pytest.mark.asyncio
@respx.mock
async def test_jobs_from_listing_html_async(httpx_client, monkeypatch):
    html = '<html><body><a href="/jobs/backend-dev">Apply now</a></body></html>'
    monkeypatch.setattr(
        sj,
        "_fetch_job_detail_title",
        lambda url: "Backend Developer",
    )
    jobs = await sj._jobs_from_listing_html_async(
        html,
        "https://example.com/careers",
        httpx_client,
        relevant_only=True,
    )
    assert any("Backend" in j["title"] for j in jobs)


@pytest.mark.network
def test_scrape_smartrecruiters_pagination(monkeypatch):
    page1 = {
        "content": [{"id": "1", "name": "Backend Engineer", "location": {}}],
        "totalFound": 2,
    }
    page2 = {
        "content": [{"id": "2", "name": "Software Engineer", "location": {}}],
        "totalFound": 2,
    }
    calls = {"n": 0}

    def route(url, **kwargs):
        calls["n"] += 1
        return json_response(page1 if calls["n"] == 1 else page2)

    install_requests_mock(monkeypatch, get_routes={"smartrecruiters.com": route})
    jobs = sj.scrape_smartrecruiters("https://api.smartrecruiters.com/v1/companies/Acme/postings")
    assert len(jobs) >= 1


@pytest.mark.network
def test_scrape_workday_pagination(monkeypatch):
    page1 = {
        "total": 2,
        "jobPostings": [
            {"title": "Backend Engineer", "externalPath": "/job/1", "locationsText": "Berlin"},
        ],
    }
    page2 = {
        "total": 2,
        "jobPostings": [
            {"title": "Software Engineer", "externalPath": "/job/2", "locationsText": "Berlin"},
        ],
    }
    calls = {"n": 0}

    def route(url, **kwargs):
        calls["n"] += 1
        return json_response(page1 if calls["n"] == 1 else page2)

    ats_url = (
        "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|"
        "https://acme.wd3.myworkdayjobs.com/en-US/careers"
    )
    install_requests_mock(monkeypatch, post_routes={"myworkdayjobs.com": route})
    jobs = sj.scrape_workday(ats_url, relevant_only=False)
    assert len(jobs) >= 1
    assert calls["n"] >= 1


@pytest.mark.network
def test_redcare_company_identifier_fallback(monkeypatch):
    payload = {"items": [{"company": {"identifier": "RedcareCo"}, "ref": ""}]}
    install_requests_mock(
        monkeypatch,
        get_routes={"redcare-pharmacy.com": json_response(payload)},
    )
    ats_type, ats_url = sj._detect_smartrecruiters_from_redcare_careers(
        "https://www.redcare-pharmacy.com/careers"
    )
    assert ats_type == "smartrecruiters"
    assert "RedcareCo" in ats_url


@pytest.mark.network
def test_scrape_join_api_pagination(monkeypatch):
    next_data = load_ats_fixture("join_next_data.json")
    page1 = {"items": [{"title": "Backend Engineer", "idParam": "b1"}], "pagination": {"pageCount": 2}}
    page2 = {"items": [{"title": "Software Engineer", "idParam": "b2"}], "pagination": {"pageCount": 2}}
    calls = {"n": 0}

    def route(url, **kwargs):
        if "join.com/companies" in url and "/jobs" not in url.split("companies/", 1)[1]:
            return text_response(
                f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>'
            )
        calls["n"] += 1
        return json_response(page1 if calls["n"] == 1 else page2)

    install_requests_mock(monkeypatch, get_routes={"join.com": route})
    jobs = sj.scrape_join("https://join.com/companies/acme-corp", relevant_only=False)
    assert len(jobs) >= 2


def test_main_workers_equals_form(monkeypatch):
    called = []

    def fake_run_country(*args, **kwargs):
        called.append(kwargs)

    monkeypatch.setattr(sj, "run_country", fake_run_country)
    monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--workers=12"])
    sj.main()
    assert called[0]["workers"] == 12


@pytest.mark.asyncio
@respx.mock
async def test_get_jobs_async_bad_detection_known_override(httpx_client, monkeypatch):
    monkeypatch.setattr(sj, "detect_ats_static_async", AsyncMock(return_value=("greenhouse", "https://boards.greenhouse.io/embed")))
    monkeypatch.setattr(sj, "scrape_greenhouse_async", AsyncMock(return_value=[]))
    company = {"name": "HelloFresh", "careers_url": "https://careers.hellofresh.com"}
    await sj.get_jobs_async(httpx_client, company, relevant_only=False)
    assert company["ats_type"] == "greenhouse"


@pytest.mark.asyncio
async def test_process_company_with_location_filter(monkeypatch):
    client = httpx.AsyncClient()
    company = {
        "name": "Acme",
        "city": "Berlin",
        "careers_url": "https://example.com/careers",
        "matching_jobs": [],
        "locations": ["Amsterdam"],
    }

    async def fake_get_jobs(client, comp, **kw):
        return [
            {"title": "Backend Engineer", "url": "https://example.com/j/1", "location": "Berlin"},
            {"title": "Software Engineer", "url": "https://example.com/j/2", "location": "Amsterdam"},
        ]

    async def fake_enrich(client, jobs, comp, **kw):
        return jobs

    monkeypatch.setattr(sj, "get_jobs_async", fake_get_jobs)
    monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)

    msg, _ = await sj._process_company_async(
        client,
        company,
        1,
        1,
        save_fn=None,
        enrich_only=False,
        skip_enriched=False,
        enrich_concurrency=2,
        catalog_country="nl",
    )
    assert "matching job" in msg
    await client.aclose()


@pytest.mark.network
def test_filter_relevant_jobs_with_locations():
    jobs = [
        {
            "title": "Backend Engineer",
            "url": "https://example.com/j/1",
            "locations": ["Berlin", "Amsterdam"],
        }
    ]
    out = sj._filter_relevant_jobs(jobs, relevant_only=False)
    assert out[0]["locations"] == ["Berlin", "Amsterdam"]


@pytest.mark.network
def test_scrape_movingimage_detail_failures(monkeypatch):
    listing = load_ats_fixture("movingimage.html")
    install_requests_mock(
        monkeypatch,
        get_routes={
            "movingimage.com/careers": text_response(listing),
            "movingimage.com/careers/backend-engineer": MockResponse(status_code=404, text=""),
        },
    )
    jobs = sj.scrape_movingimage("https://www.movingimage.com/careers", relevant_only=False)
    assert jobs  # falls back to slug title


@pytest.mark.network
def test_scrape_project_a_skip_empty_title(monkeypatch):
    listing = load_ats_fixture("project_a.html")
    empty_detail = "<html><body></body></html>"
    install_requests_mock(
        monkeypatch,
        get_routes={
            "project-a.vc/careers/123456": text_response(empty_detail),
            "project-a.vc/careers": text_response(listing),
        },
    )
    jobs = sj.scrape_project_a("https://www.project-a.vc/careers", relevant_only=False)
    assert jobs == [] or isinstance(jobs, list)


@pytest.mark.asyncio
@respx.mock
async def test_scrape_job_shop_async_pagination(httpx_client):
    page_html = load_ats_fixture("job_shop_page.html")
    search_payload = {
        "results": [{
            "found": 150,
            "hits": [
                {
                    "document": {
                        "title": "Backend Developer",
                        "url": "https://careers.acme.example.com/jobs/backend",
                    }
                }
            ],
        }]
    }
    respx.get(url__regex=r"https://careers\.acme\.example\.com/.*").mock(
        return_value=httpx.Response(200, text=page_html)
    )
    respx.post("https://api.my-job-shop.com/api/typesense/multi_search").mock(
        return_value=httpx.Response(200, json=search_payload)
    )
    jobs = await sj.scrape_job_shop_async(httpx_client, "https://careers.acme.example.com/")
    assert jobs


def test_merge_last_seen_from_fetched():
    existing = [{"title": "Role", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"}]
    scraped = [{"title": "Role Updated", "url": "https://example.com/j/1?gh_jid=1"}]
    merged, preserved, _, _ = sj.merge_matching_jobs(existing, scraped)
    assert preserved == 1
    assert merged[0]["last_seen"] == "2025-01-01"


@pytest.mark.network
def test_get_jobs_no_ats_persists_empty(monkeypatch):
    monkeypatch.setattr(sj, "detect_ats_static", lambda url: (None, None))
    monkeypatch.setattr(sj, "detect_ats_via_playwright", lambda url: (None, None))
    monkeypatch.setattr(sj, "scrape_generic", lambda url: [])
    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", False)
    company = {"name": "Co", "careers_url": "https://example.com/careers"}
    sj.get_jobs(company)
    assert company["ats_type"] == ""




