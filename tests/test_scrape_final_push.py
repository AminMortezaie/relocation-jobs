"""Final coverage push toward 90%+ on scrape_jobs.py."""

from __future__ import annotations

from unittest.mock import MagicMock

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
from tests.helpers.playwright_mock import MockPlaywrightPage, install_playwright_mock


class TestUrlExtractorEdgeCases:
    @pytest.mark.parametrize(
        "fn,url,expected_part",
        [
            (sj._extract_lever, "https://jobs.lever.co/acme", "acme"),
            (sj._extract_greenhouse, "https://boards.greenhouse.io/embed/job_board?for=slugco", "slugco"),
            (sj._extract_recruitee, "https://acme.recruitee.com/api/offers/", "acme.recruitee.com"),
            (sj._extract_workable, "https://apply.workable.com/not-api/", "workable.com"),
            (sj._extract_ashby, "https://jobs.ashbyhq.com/acme", "acme"),
        ],
    )
    def test_extractors(self, fn, url, expected_part):
        assert expected_part in fn(url)


class TestTeamtailorFeed:
    def test_listing_jobs_multiple_locations(self):
        jobs = [{
            "attributes": {"title": "Senior Software Engineer"},
            "relationships": {"locations": {"data": [
                {"id": "l1", "type": "locations"},
                {"id": "l2", "type": "locations"},
            ]}},
            "links": {"careersite-job-url": "https://acme.teamtailor.com/jobs/1"},
        }]
        included = [
            {"id": "l1", "type": "locations", "attributes": {"city": "Berlin", "country": "DE", "name": "Berlin"}},
            {"id": "l2", "type": "locations", "attributes": {"city": "Amsterdam", "country": "NL", "name": "AMS"}},
        ]
        out = sj._teamtailor_listing_jobs_from_feed(
            jobs, included, "https://acme.teamtailor.com/jobs", relevant_only=True,
        )
        assert out[0]["locations"]


class TestPersonioHtmlParsing:
    @pytest.mark.network
    def test_personio_html_short_title_skipped(self, monkeypatch):
        html = '<html><body><a href="/job/1">Go</a></body></html>'
        install_requests_mock(
            monkeypatch,
            get_routes={"personio.de": text_response(html)},
        )
        assert sj.scrape_personio_html("https://acme.jobs.personio.de") == []

    @pytest.mark.network
    def test_personio_html_link_without_h3(self, monkeypatch):
        html = '<html><body><a href="/job/99">Backend Engineer Platform</a></body></html>'
        install_requests_mock(
            monkeypatch,
            get_routes={"personio.de": text_response(html)},
        )
        jobs = sj.scrape_personio_html("https://acme.jobs.personio.de")
        assert jobs[0]["title"] == "Backend Engineer Platform"


class TestApplyToJobEdgeCases:
    @pytest.mark.network
    def test_applytojob_skips_invalid_links(self, monkeypatch):
        html = """
        <html><body>
          <a href="/apply/">Apply</a>
          <a href="/apply/jobs/list">Jobs</a>
          <a href="/apply/42/backend-engineer">Backend Engineer</a>
        </body></html>
        """
        install_requests_mock(
            monkeypatch,
            get_routes={"applytojob.com": text_response(html)},
        )
        jobs = sj.scrape_applytojob("https://acme.applytojob.com/", relevant_only=True)
        assert len(jobs) == 1


class TestGetJobsKnownPath:
    @pytest.mark.network
    def test_get_jobs_known_without_cache(self, monkeypatch):
        monkeypatch.setattr(
            sj,
            "scrape_greenhouse",
            lambda url: [{"title": "Backend Engineer", "url": "https://example.com/j/1"}],
        )
        company = {"name": "HelloFresh", "careers_url": "https://careers.hellofresh.com"}
        jobs = sj.get_jobs(company)
        assert company["ats_type"] == "greenhouse"
        assert jobs


class TestDetectAtsForHintGuessed:
    def test_guess_url_when_no_match(self, monkeypatch):
        monkeypatch.setattr(
            sj,
            "_detect_ats_in_html_for_hint",
            lambda url, hint: (None, None),
        )
        monkeypatch.setattr(sj, "detect_ats_via_playwright", lambda *a, **k: (None, None))
        ats_type, ats_url = sj.detect_ats_for_hint(
            "Acme Corp",
            "https://example.com/careers",
            "greenhouse",
        )
        assert ats_type == "greenhouse"
        assert "greenhouse.io" in ats_url


class TestPlaywrightErrorPaths:
    def test_scrape_jibe_error(self, monkeypatch):
        from contextlib import contextmanager

        @contextmanager
        def broken_cm():
            raise RuntimeError("fail")
            yield  # pragma: no cover

        monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
        monkeypatch.setattr(sj, "sync_playwright", broken_cm)
        assert sj.scrape_jibe("https://jobs.booking.com/jobs") == []

    def test_scrape_atlassian_error(self, monkeypatch):
        from contextlib import contextmanager

        @contextmanager
        def broken_cm():
            raise RuntimeError("fail")
            yield  # pragma: no cover

        monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
        monkeypatch.setattr(sj, "sync_playwright", broken_cm)
        assert sj.scrape_atlassian("https://www.atlassian.com/careers") == []


class TestScrapeTeamtailorBoardUrl:
    @pytest.mark.network
    def test_scrape_teamtailor_board_url_only(self, monkeypatch, pw_enabled_unused=None):
        install_requests_mock(
            monkeypatch,
            get_routes={"teamtailor.com": MockResponse(status_code=404, text="")},
        )
        monkeypatch.setattr(
            sj,
            "scrape_with_playwright",
            lambda url, **kw: [{"title": "Backend Engineer", "url": "https://example.com/j/1"}],
        )
        jobs = sj.scrape_teamtailor(
            "https://acme.teamtailor.com/jobs",
            "https://acme.teamtailor.com/jobs",
        )
        assert jobs


class TestBolAndJobShopExceptions:
    @pytest.mark.network
    def test_scrape_bol_request_exception(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("down")

        monkeypatch.setattr(sj.requests, "post", boom)
        assert sj.scrape_bol("https://careers.bol.com/en/jobs/") == []

    @pytest.mark.network
    def test_scrape_job_shop_post_exception(self, monkeypatch):
        page_html = load_ats_fixture("job_shop_page.html")
        install_requests_mock(
            monkeypatch,
            get_routes={"careers.acme.example.com": text_response(page_html)},
        )

        def boom(url, **kwargs):
            raise ConnectionError("down")

        monkeypatch.setattr(sj.requests, "post", boom)
        assert sj.scrape_job_shop("https://careers.acme.example.com/") == []


class TestListingHtmlEdgeCases:
    @pytest.mark.network
    def test_listing_skips_irrelevant_after_detail(self, monkeypatch):
        html = '<html><body><a href="/jobs/x">Apply now</a></body></html>'
        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": text_response("<html><body><h1>Marketing Manager</h1></body></html>")},
        )
        jobs = sj._jobs_from_listing_html(html, "https://example.com/careers", relevant_only=True)
        assert jobs == []

    def test_review_entry_noise(self):
        assert sj._review_entry({"title": "Backend", "url": "https://example.com/jobs/show_more"}) is None


class TestMainAllCountries:
    def test_main_all_countries(self, monkeypatch):
        calls = []

        def fake_run_country(key, **kwargs):
            calls.append(key)

        monkeypatch.setattr(sj, "run_country", fake_run_country)
        monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--all"])
        sj.main()
        from relocation_jobs.paths import COUNTRY_FILE_NAMES
        assert len(calls) == len(COUNTRY_FILE_NAMES)


class TestRunFileNoHttpx:
    def test_run_file_async_requires_httpx(self, monkeypatch):
        monkeypatch.setattr(sj, "HTTPX_AVAILABLE", False)
        with pytest.raises(SystemExit):
            import asyncio
            asyncio.run(sj.run_file_async("test"))


class TestWorkableBadSlug:
    @pytest.mark.network
    def test_workable_missing_slug(self, monkeypatch):
        assert sj.scrape_workable("https://apply.workable.com/api/v3/accounts/") == []


class TestDeelJoinErrors:
    @pytest.mark.network
    def test_deel_fetch_error(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("down")

        monkeypatch.setattr(sj.requests, "get", boom)
        assert sj.scrape_deel("https://jobs.deel.com/acme") == []

    @pytest.mark.network
    def test_join_fetch_error(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("down")

        monkeypatch.setattr(sj.requests, "get", boom)
        assert sj.scrape_join("https://join.com/companies/acme") == []


class TestJibeNextPageClick:
    def test_jibe_clicks_next_page(self, monkeypatch):
        page = MockPlaywrightPage(
            evaluate_results=[
                [{"h": "https://jobs.booking.com/booking/jobs/r1", "t": "Backend Engineer"}],
                [{"h": "https://jobs.booking.com/booking/jobs/r2", "t": "Software Engineer"}],
            ],
        )
        next_btn = MagicMock()
        next_btn.get_attribute.side_effect = [None, "true"]
        page.query_selector = MagicMock(return_value=next_btn)
        install_playwright_mock(monkeypatch, page=page, available=True)
        jobs = sj.scrape_jibe("https://jobs.booking.com/booking/jobs", relevant_only=False)
        assert len(jobs) >= 2


@pytest.mark.asyncio
async def test_process_company_full_status_message(monkeypatch):
    client = httpx.AsyncClient()
    company = {
        "name": "Acme",
        "city": "Berlin",
        "careers_url": "https://example.com/careers",
        "matching_jobs": [
            {
                "title": "Old Role",
                "url": "https://example.com/j/1?gh_jid=1",
                "fetched": "2025-01-01",
                "applied": True,
            },
            {
                "title": "Stale Role",
                "url": "https://example.com/j/99?gh_jid=99",
                "fetched": "2024-01-01",
            },
        ],
    }

    async def fake_get_jobs(client, comp, **kw):
        return [
            {"title": "Old Role Updated", "url": "https://example.com/j/1?gh_jid=1"},
            {"title": "Backend Engineer New", "url": "https://example.com/j/2?gh_jid=2"},
        ]

    async def fake_enrich(client, jobs, comp, **kw):
        for j in jobs:
            j["visa_sponsorship"] = True
        return jobs

    monkeypatch.setattr(sj, "get_jobs_async", fake_get_jobs)
    monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)

    msg, new_count = await sj._process_company_async(
        client,
        company,
        1,
        1,
        save_fn=None,
        enrich_only=False,
        skip_enriched=False,
        enrich_concurrency=2,
    )
    assert new_count >= 0
    assert "matching job" in msg
    assert len(company["matching_jobs"]) >= 2
    await client.aclose()


@pytest.mark.network
def test_fetch_greenhouse_no_matching_board(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={"boards-api.greenhouse.io": MockResponse(status_code=404, text="")},
    )
    assert sj._fetch_greenhouse_job_text("https://boards.greenhouse.io/unknown/jobs/999") == ""


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "fn,url,method,route",
    [
        (sj.scrape_bol_async, "https://careers.bol.com/en/jobs/", "post", "careers.bol.com"),
        (sj.scrape_deel_async, "https://jobs.deel.com/acme", "get", "jobs.deel.com"),
        (sj.scrape_workable_async, "https://apply.workable.com/acme/", "post", "apply.workable.com"),
        (sj.scrape_recruitee_async, "https://acme.recruitee.com/", "get", "recruitee.com"),
        (sj.scrape_smartrecruiters_async, "https://api.smartrecruiters.com/v1/companies/X/postings", "get", "smartrecruiters.com"),
        (sj.scrape_workday_async, "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|https://acme.wd3.myworkdayjobs.com/en-US/careers", "post", "myworkdayjobs.com"),
        (sj.scrape_ashby_async, "https://jobs.ashbyhq.com/acme", "get", "ashbyhq.com"),
        (sj.scrape_greenhouse_async, "https://boards.greenhouse.io/acme", "get", "greenhouse.io"),
    ],
)
async def test_async_scraper_error_paths(fn, url, method, route):
    client = httpx.AsyncClient()
    if method == "post":
        respx.post(url__regex=rf".*{route}.*").mock(return_value=httpx.Response(500, text="err"))
    else:
        respx.get(url__regex=rf".*{route}.*").mock(return_value=httpx.Response(500, text="err"))
    if fn is sj.scrape_ashby_async:
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(sj, "scrape_with_playwright", lambda *a, **k: [])
        try:
            result = await fn(client, url)
        finally:
            monkeypatch.undo()
    else:
        result = await fn(client, url)
    assert result == []
    await client.aclose()


@pytest.mark.network
def test_personio_fetch_error_paths(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("offline")

    monkeypatch.setattr(sj.requests, "get", boom)
    assert sj.scrape_personio_com_api("https://www.personio.com/api/careers/jobs/list") == []
    assert sj.scrape_personio_html("https://acme.jobs.personio.de") == []


def test_merge_visa_from_scrape_when_old_missing():
    existing = [{"title": "Role", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"}]
    scraped = [{"title": "Role", "url": "https://example.com/j/1?gh_jid=1", "visa_sponsorship": True}]
    merged, _, _, _ = sj.merge_matching_jobs(existing, scraped)
    assert merged[0].get("visa_sponsorship") is True


def test_enrich_one_job_only_missing_visa_already_set(monkeypatch):
    monkeypatch.setattr(sj, "fetch_job_description", lambda *a, **k: "should not run")
    job = {"title": "Backend Engineer", "url": "https://example.com/j/1", "visa_sponsorship": False}
    sj._enrich_one_job(job, None, "2025-06-01", only_missing=True)
    assert job["fetched"] == "2025-06-01"


@pytest.mark.asyncio
@respx.mock
async def test_scrape_job_shop_async_post_error():
    client = httpx.AsyncClient()
    page_html = load_ats_fixture("job_shop_page.html")
    respx.get(url__regex=r"https://careers\.acme\.example\.com/.*").mock(
        return_value=httpx.Response(200, text=page_html)
    )
    respx.post("https://api.my-job-shop.com/api/typesense/multi_search").mock(
        return_value=httpx.Response(500, text="err")
    )
    result = await sj.scrape_job_shop_async(client, "https://careers.acme.example.com/")
    assert result == []
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_scrape_join_async_fetch_error():
    client = httpx.AsyncClient()
    respx.get("https://join.com/companies/acme").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_join_async(client, "https://join.com/companies/acme") == []
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_scrape_generic_async_error():
    client = httpx.AsyncClient()
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_generic_async(client, "https://example.com/careers") == []
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_detect_ats_static_async_error():
    client = httpx.AsyncClient()
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.detect_ats_static_async(client, "https://example.com/careers") == (None, None)
    await client.aclose()


@pytest.mark.network
def test_get_jobs_bad_slug_known_correction(monkeypatch):
    monkeypatch.setattr(
        sj,
        "detect_ats_static",
        lambda url: ("greenhouse", "https://boards.greenhouse.io/embed"),
    )
    monkeypatch.setattr(sj, "detect_ats_via_playwright", lambda url: (None, None))
    monkeypatch.setattr(sj, "scrape_greenhouse", MagicMock(return_value=[]))
    company = {"name": "HelloFresh", "careers_url": "https://careers.hellofresh.com"}
    sj.get_jobs(company)
    assert company["ats_url"] == sj.KNOWN_ATS["HelloFresh"][1]


def test_main_workers_flag(monkeypatch):
    called = []

    def fake_run_country(*args, **kwargs):
        called.append(kwargs)

    monkeypatch.setattr(sj, "run_country", fake_run_country)
    monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--workers", "6"])
    sj.main()
    assert called[0]["workers"] == 6


def test_enrich_jobs_empty_list():
    assert sj.enrich_jobs([], {"ats_type": None}) == []


@pytest.mark.asyncio
@respx.mock
async def test_scrape_smartrecruiters_async_no_company_id():
    client = httpx.AsyncClient()
    assert await sj.scrape_smartrecruiters_async(client, "https://example.com/bad") == []
    await client.aclose()


@pytest.mark.network
def test_scrape_smartrecruiters_no_company_id():
    assert sj.scrape_smartrecruiters("https://example.com/bad") == []


@pytest.mark.network
def test_scrape_workday_skips_empty_postings(monkeypatch):
    payload = {
        "total": 1,
        "jobPostings": [{"title": "", "externalPath": "/job/empty"}],
    }
    install_requests_mock(
        monkeypatch,
        post_routes={"myworkdayjobs.com": json_response(payload)},
    )
    ats_url = (
        "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|"
        "https://acme.wd3.myworkdayjobs.com/en-US/careers"
    )
    assert sj.scrape_workday(ats_url) == []


@pytest.mark.network
def test_scrape_epam_no_next_data(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={"careers.epam.com": text_response("<html></html>")},
    )
    assert sj.scrape_epam("https://careers.epam.com/") == []



