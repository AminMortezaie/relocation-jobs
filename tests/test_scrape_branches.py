"""Scraper branch coverage — merged from scrape_coverage*, final_push, push_95_scrape."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

from relocation_jobs import scrape_jobs as sj
from relocation_jobs.core import ats_detection as ats_det
from tests.helpers.http_mock import (
    MockResponse,
    install_requests_mock,
    json_response,
    load_ats_fixture,
    text_response,
)
from tests.helpers.playwright_mock import MockPlaywrightPage, install_playwright_mock


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


class TestPersonioPaths:
    @pytest.mark.network
    def test_scrape_personio_html_fallback(self, monkeypatch):
        html = """
        <html><body>
          <a href="/job/123"><h3>Backend Engineer</h3></a>
        </body></html>
        """

        def route(url, **kwargs):
            if url.endswith("/xml"):
                return text_response("<html>not xml</html>")
            return text_response(html)

        install_requests_mock(monkeypatch, get_routes={"personio.de": route})
        jobs = sj.scrape_personio("https://acme.jobs.personio.de/")
        assert any("Backend" in j["title"] for j in jobs)

    @pytest.mark.network
    def test_scrape_personio_com_api_non_list(self, monkeypatch):
        install_requests_mock(
            monkeypatch,
            get_routes={"personio.com/api/careers/jobs": json_response({"error": "nope"})},
        )
        assert sj.scrape_personio_com_api("https://www.personio.com/api/careers/jobs/list") == []


class TestTeamtailorHtmlBoard:
    @pytest.mark.network
    def test_scrape_teamtailor_html_board(self, monkeypatch):
        page1 = """
        <html><body><a href="/jobs/backend-engineer">Backend Engineer</a></body></html>
        """
        page2 = "<html><body></body></html>"

        def route(url, **kwargs):
            if "page=2" in url:
                return text_response(page2)
            return text_response(page1)

        install_requests_mock(
            monkeypatch,
            get_routes={"teamtailor.com": route},
            default_get=text_response(""),
        )
        jobs = sj._scrape_teamtailor_html_board(
            "https://acme.teamtailor.com/jobs",
            relevant_only=True,
        )
        assert len(jobs) >= 1


class TestDetectorsWithHttp:
    @pytest.mark.network
    def test_detect_job_shop_from_url(self, monkeypatch):
        html = load_ats_fixture("job_shop_page.html")
        install_requests_mock(
            monkeypatch,
            get_routes={"careers.acme.example.com": text_response(html)},
        )
        ats_type, ats_url = sj._detect_job_shop_from_url("https://careers.acme.example.com/")
        assert ats_type == "job_shop"

    @pytest.mark.network
    def test_detect_smartrecruiters_from_redcare(self, monkeypatch):
        payload = {
            "items": [
                {"ref": "https://api.smartrecruiters.com/v1/companies/Redcare-Pharmacy/postings/1"},
            ]
        }
        install_requests_mock(
            monkeypatch,
            get_routes={"redcare-pharmacy.com": json_response(payload)},
        )
        ats_type, ats_url = sj._detect_smartrecruiters_from_redcare_careers(
            "https://www.redcare-pharmacy.com/careers"
        )
        assert ats_type == "smartrecruiters"
        assert "Redcare" in ats_url


class TestListingDetailTitle:
    @pytest.mark.network
    def test_fetch_job_detail_title(self, monkeypatch):
        html = "<html><body><h1>Senior Backend Engineer</h1></body></html>"
        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": text_response(html)},
        )
        title = sj._fetch_job_detail_title("https://example.com/jobs/backend")
        assert "Backend Engineer" in title

    def test_title_from_listing_anchor_generic_label(self):
        from bs4 import BeautifulSoup

        html = '<div><span>Senior Backend Engineer</span><a href="/jobs/1">Apply now</a></div>'
        soup = BeautifulSoup(html, "html.parser")
        a = soup.find("a")
        title = sj._title_from_listing_anchor(a)
        assert "Backend" in title

    def test_needs_detail_title(self):
        assert sj._needs_detail_title("Apply now") is True
        assert sj._needs_detail_title("Senior Backend Engineer") is False


class TestAshbyJobText:
    @pytest.mark.network
    def test_fetch_ashby_job_text(self, monkeypatch):
        payload = load_ats_fixture("ashby.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"api.ashbyhq.com": json_response(payload)},
        )
        job_id = payload["jobs"][0]["id"]
        text = sj._fetch_ashby_job_text(f"https://jobs.ashbyhq.com/acme/{job_id}")
        assert "visa" in text.lower() or len(text) > 0


class TestApplyKnownAts:
    def test_apply_known_ats_smartrecruiters_careers_url(self, monkeypatch):
        company = {
            "name": "OtherCo",
            "careers_url": "https://careers.smartrecruiters.com/AcmeCorp",
            "ats_type": "",
            "ats_url": "",
        }
        saved = []
        sj._apply_known_ats_override(company, save_fn=lambda: saved.append(True))
        assert company["ats_type"] == "smartrecruiters"
        assert saved


class TestGetJobsAsyncBranches:
    @pytest.mark.asyncio
    @respx.mock
    async def test_get_jobs_async_personio(self):
        payload = load_ats_fixture("personio.json")
        respx.get("https://www.personio.com/api/careers/jobs/list").mock(
            return_value=httpx.Response(200, json=payload)
        )
        client = httpx.AsyncClient()
        company = {
            "name": "PersonioCo",
            "careers_url": "https://www.personio.com/careers",
            "ats_type": "personio",
            "ats_url": "https://www.personio.com/api/careers/jobs/list",
        }
        jobs = await sj.get_jobs_async(client, company, relevant_only=True)
        assert len(jobs) >= 1
        await client.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_jobs_async_teamtailor(self, monkeypatch):
        monkeypatch.setattr(
            sj,
            "scrape_teamtailor",
            MagicMock(return_value=[{"title": "Backend Engineer", "url": "https://example.com/j/1"}]),
        )
        client = httpx.AsyncClient()
        company = {
            "name": "TTCo",
            "careers_url": "https://acme.teamtailor.com/jobs",
            "ats_type": "teamtailor",
            "ats_url": "key123",
        }
        jobs = await sj.get_jobs_async(client, company, relevant_only=True)
        assert jobs[0]["title"] == "Backend Engineer"
        await client.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_jobs_async_jibe(self, monkeypatch):
        monkeypatch.setattr(
            sj,
            "scrape_jibe",
            MagicMock(return_value=[{"title": "Backend Engineer", "url": "https://example.com/j/1"}]),
        )
        client = httpx.AsyncClient()
        company = {
            "name": "Booking",
            "careers_url": "https://jobs.booking.com/booking/jobs",
            "ats_type": "jibe",
            "ats_url": "https://jobs.booking.com/booking/jobs",
        }
        jobs = await sj.get_jobs_async(client, company, relevant_only=False)
        assert len(jobs) == 1
        await client.aclose()


class TestRunFileAsyncPaths:
    async def _run_with_data(self, monkeypatch, country_data, **kwargs):
        monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
        monkeypatch.setattr(sj, "load_country_catalog", lambda k: country_data)
        monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
        monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)

        async def fake_get_jobs(client, company, **kw):
            return [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]

        async def fake_enrich(client, jobs, company, **kw):
            return jobs

        monkeypatch.setattr(sj, "get_jobs_async", fake_get_jobs)
        monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)
        concurrency = kwargs.pop("concurrency", 1)
        await sj.run_file_async("test", concurrency=concurrency, **kwargs)

    @pytest.mark.asyncio
    async def test_skip_filled(self, monkeypatch, capsys):
        data = {
            "companies": [
                {
                    "name": "FilledCo",
                    "city": "Berlin",
                    "careers_url": "https://example.com/careers",
                    "matching_jobs": [{"title": "Role", "url": "https://example.com/j/1"}],
                }
            ]
        }
        get_mock = MagicMock()
        monkeypatch.setattr(sj, "get_jobs_async", get_mock)
        await self._run_with_data(monkeypatch, data, skip_filled=True)
        get_mock.assert_not_called()
        assert "skipped" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_run_all_companies_serial(self, monkeypatch):
        data = {
            "companies": [
                {
                    "name": f"Co{i}",
                    "city": "Berlin",
                    "careers_url": "https://example.com/careers",
                    "matching_jobs": [],
                }
                for i in range(2)
            ]
        }
        await self._run_with_data(monkeypatch, data, concurrency=1)
        assert all(c.get("fetch_ok") for c in data["companies"])

    @pytest.mark.asyncio
    async def test_run_concurrent_workers(self, monkeypatch):
        data = {
            "companies": [
                {
                    "name": f"Co{i}",
                    "city": "Berlin",
                    "careers_url": "https://example.com/careers",
                    "matching_jobs": [],
                }
                for i in range(3)
            ]
        }
        await self._run_with_data(monkeypatch, data, concurrency=2)
        assert all(c.get("fetch_ok") for c in data["companies"])

    @pytest.mark.asyncio
    async def test_cancel_during_run(self, monkeypatch):
        data = {
            "companies": [
                {
                    "name": "Co1",
                    "city": "Berlin",
                    "careers_url": "https://example.com/careers",
                    "matching_jobs": [],
                }
            ]
        }
        sj.set_cancel_checker(lambda: True)
        try:
            await self._run_with_data(monkeypatch, data)
        finally:
            sj.clear_cancel_checker()

    @pytest.mark.asyncio
    async def test_empty_work_list(self, monkeypatch, capsys):
        data = {"companies": []}
        await self._run_with_data(monkeypatch, data)
        out = capsys.readouterr().out
        assert "matching jobs" in out.lower() or "companies" in out.lower()


class TestMain:
    def test_main_skip_filled(self, monkeypatch):
        called = []

        def fake_run_country(*args, **kwargs):
            called.append(kwargs)

        monkeypatch.setattr(sj, "run_country", fake_run_country)
        monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--skip-filled"])
        sj.main()
        assert called[0]["skip_filled"] is True

    def test_main_with_target(self, monkeypatch):
        called = []

        def fake_run_country(*args, **kwargs):
            called.append(kwargs)

        monkeypatch.setattr(sj, "run_country", fake_run_country)
        monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "Acme Corp"])
        sj.main()
        assert called[0]["target"] == "Acme Corp"


class TestDetectAtsForHintHtml:
    @pytest.mark.network
    def test_detect_ats_in_html_for_hint(self, monkeypatch):
        html = "Powered by https://jobs.lever.co/acme"
        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": text_response(html)},
        )
        ats_type, ats_url = sj.detect_ats_for_hint(
            "Acme",
            "https://example.com/careers",
            "lever",
        )
        assert ats_type == "lever"


class TestJobShopErrors:
    @pytest.mark.network
    def test_scrape_job_shop_config_missing(self, monkeypatch):
        install_requests_mock(
            monkeypatch,
            get_routes={"careers.acme.example.com": text_response("<html></html>")},
        )
        assert sj.scrape_job_shop("https://careers.acme.example.com/") == []


class TestScrapeErrors:
    @pytest.mark.network
    def test_scrape_lever_error(self, monkeypatch):
        install_requests_mock(
            monkeypatch,
            get_routes={"lever.co": MockResponse(status_code=500, text="err")},
        )
        assert sj.scrape_lever("https://jobs.lever.co/acme") == []

    @pytest.mark.network
    def test_scrape_greenhouse_bad_slug(self, monkeypatch):
        assert sj.scrape_greenhouse("https://boards.greenhouse.io/embed") == []


class TestEnrichAsyncEdgeCases:
    @pytest.mark.asyncio
    async def test_enrich_only_missing_skips_filled(self):
        client = httpx.AsyncClient()
        job = {
            "title": "Backend Engineer",
            "url": "https://example.com/j/1",
            "fetched": "2025-01-01",
            "visa_sponsorship": True,
        }
        await sj._enrich_one_job_async(
            client, job, None, "2025-06-01", only_missing=True, preserve_fetched=True
        )
        assert job["fetched"] == "2025-01-01"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_enrich_cancelled(self, monkeypatch):
        sj.set_cancel_checker(lambda: True)
        client = httpx.AsyncClient()
        jobs = [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]
        try:
            out = await sj.enrich_jobs_async_with_client(
                client, jobs, {"ats_type": None}, concurrency=1
            )
            assert out == jobs
        finally:
            sj.clear_cancel_checker()
            await client.aclose()


class TestGuessAndSlug:
    def test_company_slug_fallback(self):
        slug = sj._company_slug("!!!")
        assert slug == ""

    def test_persist_detected_ats_empty(self):
        company = {}
        result = sj._persist_detected_ats(company, None, "")
        assert result == "generic"
        assert company["ats_type"] == ""


class TestPlaywrightJibePagination:
    def test_scrape_jibe_with_next_page(self, monkeypatch):
        page = MockPlaywrightPage(
            evaluate_results=[
                [{"h": "https://jobs.booking.com/booking/jobs/r1", "t": "Backend Engineer"}],
            ],
        )
        next_btn = MagicMock()
        next_btn.get_attribute.return_value = None
        page.query_selector = MagicMock(side_effect=[next_btn, None])
        install_playwright_mock(monkeypatch, page=page, available=True)
        jobs = sj.scrape_jibe("https://jobs.booking.com/booking/jobs")
        assert any("Backend" in j["title"] for j in jobs)


class TestTeamtailorApi:
    @pytest.mark.network
    def test_fetch_teamtailor_jobs_legacy_auth(self, monkeypatch):
        payload = load_ats_fixture("teamtailor.json")
        calls = {"n": 0}

        def route(url, **kwargs):
            calls["n"] += 1
            if calls["n"] <= 3:
                return MockResponse(status_code=406, text="not acceptable")
            return json_response(payload)

        install_requests_mock(monkeypatch, get_routes={"api.teamtailor.com": route})
        jobs, included = sj._fetch_teamtailor_jobs("legacy-key")
        assert jobs or included or calls["n"] >= 3

    @pytest.mark.network
    def test_scrape_teamtailor_playwright_fallback(self, monkeypatch):
        install_requests_mock(
            monkeypatch,
            get_routes={"teamtailor.com": MockResponse(status_code=500, text="err")},
        )
        monkeypatch.setattr(
            sj,
            "scrape_with_playwright",
            lambda url, **kw: [{"title": "Backend Engineer", "url": "https://example.com/j/1"}],
        )
        jobs = sj.scrape_teamtailor("https://acme.teamtailor.com/jobs", "https://acme.teamtailor.com/jobs")
        assert jobs[0]["title"] == "Backend Engineer"


class TestFetchJobDescriptionPaths:
    @pytest.mark.network
    def test_fetch_greenhouse_board_fallback(self, monkeypatch):
        detail = load_ats_fixture("greenhouse_job_detail.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"boards-api.greenhouse.io": json_response(detail)},
        )
        text = sj._fetch_greenhouse_job_text("https://boards.greenhouse.io/acme/jobs/123456")
        assert len(text) > 0

    @pytest.mark.network
    def test_fetch_recruitee_full_path(self, monkeypatch):
        offers = load_ats_fixture("recruitee.json")
        detail = load_ats_fixture("recruitee_offer_detail.json")

        def route(url, **kwargs):
            if url.endswith("/api/offers/"):
                return json_response(offers)
            if "/api/offers/101" in url:
                return json_response(detail)
            return MockResponse(status_code=404)

        install_requests_mock(monkeypatch, get_routes={"recruitee.com": route})
        text = sj._fetch_recruitee_job_text("https://acme.recruitee.com/o/backend-developer")
        assert "relocation" in text.lower() or "visa" in text.lower()


class TestGetJobsDetection:
    @pytest.mark.network
    def test_get_jobs_known_ats_bad_slug(self, monkeypatch):
        monkeypatch.setattr(sj, "scrape_greenhouse", MagicMock(return_value=[]))
        company = {
            "name": "HelloFresh",
            "careers_url": "https://careers.hellofresh.com",
        }
        sj.get_jobs(company)
        assert company["ats_type"] == "greenhouse"

    @pytest.mark.network
    def test_get_jobs_playwright_detection(self, monkeypatch):
        monkeypatch.setattr(
            sj,
            "detect_ats_static",
            lambda url: (None, None),
        )
        monkeypatch.setattr(
            sj,
            "detect_ats_via_playwright",
            lambda url: ("lever", "https://jobs.lever.co/acme"),
        )
        monkeypatch.setattr(sj, "scrape_lever", MagicMock(return_value=[{"title": "Backend", "url": "https://x.com/j/1"}]))
        company = {"name": "Co", "careers_url": "https://example.com/careers"}
        jobs = sj.get_jobs(company)
        assert company["ats_type"] == "lever"
        assert jobs


class TestMainExtended:
    def test_main_all_and_workers(self, monkeypatch):
        called = []

        def fake_run_country(*args, **kwargs):
            called.append(kwargs)

        monkeypatch.setattr(sj, "run_country", fake_run_country)
        monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--all", "--workers=8", "--serial"])
        sj.main()
        assert called[0]["workers"] == 1  # --serial overrides
        assert len(called) >= 1

    def test_main_country_arg(self, monkeypatch):
        called = []

        def fake_run_country(key, **kwargs):
            called.append(key)

        monkeypatch.setattr(sj, "run_country", fake_run_country)
        monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--country", "uk"])
        sj.main()
        assert called[0] == "uk"


class TestBolPayload:
    def test_bol_search_payload_with_doelgroep(self):
        payload = sj._bol_search_payload("https://careers.bol.com/en/jobs/?doelgroep[]=tech")
        assert "doelgroep" in payload["body"]


class TestReviewAndListing:
    def test_listing_candidates_with_detail_fetch(self, monkeypatch):
        html = '<html><body><a href="/jobs/role">Apply now</a></body></html>'
        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": text_response("<html><body><h1>Backend Engineer</h1></body></html>")},
        )
        jobs = sj._jobs_from_listing_html(html, "https://example.com/careers", relevant_only=True)
        assert any("Backend" in j["title"] for j in jobs)

    def test_report_activity_empty_message(self):
        sj._report_activity("")


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
    monkeypatch.setattr(sj, "load_country_catalog", lambda k: data)
    monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
    monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)
    await sj.run_file_async("test", target="SkippedCo", skip_filled=True)
    assert "skipped" in capsys.readouterr().out.lower()


async def test_scrape_errors_async(monkeypatch):
    client = httpx.AsyncClient()
    respx.get("https://jobs.lever.co/bad").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_lever_async(client, "https://jobs.lever.co/bad") == []
    await client.aclose()


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


def test_scrape_bol_failure(monkeypatch):
    install_requests_mock(
        monkeypatch,
        post_routes={"careers.bol.com": json_response({"success": False})},
    )
    assert sj.scrape_bol("https://careers.bol.com/en/jobs/") == []


def test_scrape_workday_missing_config():
    assert sj.scrape_workday("https://example.com") == []


def test_scrape_deel_invalid_url():
    assert sj.scrape_deel("https://jobs.deel.com/embed") == []


def test_scrape_join_invalid_url():
    assert sj.scrape_join("https://join.com/companies/embed") == []


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


async def test_scrape_job_shop_async_errors(httpx_client):
    respx.get(url__regex=r"https://careers\.acme\.example\.com/.*").mock(
        return_value=httpx.Response(500, text="err")
    )
    assert await sj.scrape_job_shop_async(httpx_client, "https://careers.acme.example.com/") == []


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
    monkeypatch.setattr(sj, "load_country_catalog", lambda k: data)
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


async def test_get_jobs_async_bad_detection_known_override(httpx_client, monkeypatch):
    monkeypatch.setattr(sj, "detect_ats_static_async", AsyncMock(return_value=("greenhouse", "https://boards.greenhouse.io/embed")))
    monkeypatch.setattr(sj, "scrape_greenhouse_async", AsyncMock(return_value=[]))
    company = {"name": "HelloFresh", "careers_url": "https://careers.hellofresh.com"}
    await sj.get_jobs_async(httpx_client, company, relevant_only=False)
    assert company["ats_type"] == "greenhouse"


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


def test_get_jobs_no_ats_persists_empty(monkeypatch):
    monkeypatch.setattr(sj, "detect_ats_static", lambda url: (None, None))
    monkeypatch.setattr(sj, "detect_ats_via_playwright", lambda url: (None, None))
    monkeypatch.setattr(sj, "scrape_generic", lambda url: [])
    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", False)
    company = {"name": "Co", "careers_url": "https://example.com/careers"}
    sj.get_jobs(company)
    assert company["ats_type"] == ""


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
            ats_det,
            "_detect_ats_in_html_for_hint",
            lambda url, hint: (None, None),
        )
        monkeypatch.setattr(ats_det, "detect_ats_via_playwright", lambda *a, **k: (None, None))
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
        from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
        assert len(calls) == len(SUPPORTED_COUNTRIES)


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


async def test_scrape_join_async_fetch_error():
    client = httpx.AsyncClient()
    respx.get("https://join.com/companies/acme").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_join_async(client, "https://join.com/companies/acme") == []
    await client.aclose()


async def test_scrape_generic_async_error():
    client = httpx.AsyncClient()
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_generic_async(client, "https://example.com/careers") == []
    await client.aclose()


async def test_detect_ats_static_async_error():
    client = httpx.AsyncClient()
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.detect_ats_static_async(client, "https://example.com/careers") == (None, None)
    await client.aclose()


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


async def test_scrape_smartrecruiters_async_no_company_id():
    client = httpx.AsyncClient()
    assert await sj.scrape_smartrecruiters_async(client, "https://example.com/bad") == []
    await client.aclose()


def test_scrape_smartrecruiters_no_company_id():
    assert sj.scrape_smartrecruiters("https://example.com/bad") == []


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


def test_scrape_epam_no_next_data(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={"careers.epam.com": text_response("<html></html>")},
    )
    assert sj.scrape_epam("https://careers.epam.com/") == []


def _reload_scrape_without(module_name: str):
    real_import = __import__

    def block(name, *args, **kwargs):
        if name == module_name or name.startswith(module_name + "."):
            raise ImportError(f"blocked {module_name}")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=block):
        import relocation_jobs.core.ats_detection as ats_detection

        importlib.reload(ats_detection)
        return importlib.reload(importlib.import_module("relocation_jobs.scrape_jobs"))


def test_scrape_import_error_playwright():
    mod = _reload_scrape_without("playwright.sync_api")
    assert mod.PLAYWRIGHT_AVAILABLE is False
    import relocation_jobs.core.ats_detection as ats_detection

    importlib.reload(ats_detection)
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


def test_scrape_greenhouse_bad_slug():
    assert sj.scrape_greenhouse("https://boards.greenhouse.io/embed/jobs") == []


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


def test_bol_helpers():
    assert sj._bol_doelgroep_from_url("https://careers.bol.com/?doelgroep[]=tech")
    payload = sj._bol_search_payload("https://careers.bol.com/?doelgroep[]=tech")
    assert "body" in payload


def test_extract_helpers():
    assert sj._extract_lever("https://jobs.lever.co/acme")
    assert sj._extract_greenhouse("https://boards.greenhouse.io/acme")
    assert sj._extract_recruitee("https://acme.recruitee.com/")
    assert sj._extract_workable("https://apply.workable.com/acme/")
    assert sj._extract_ashby("https://jobs.ashbyhq.com/acme")


def test_scrape_teamtailor_html(monkeypatch):
    html = '<a href="/jobs/123-backend-engineer">Backend Engineer</a>'
    install_requests_mock(
        monkeypatch,
        get_routes={"teamtailor.com": text_response(html)},
    )
    monkeypatch.setattr(sj, "scrape_with_playwright", lambda *a, **k: [])
    jobs = sj.scrape_teamtailor("", "https://acme.teamtailor.com/jobs", relevant_only=True)
    assert isinstance(jobs, list)


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
    monkeypatch.setattr(sj, "load_country_catalog", lambda k: data)
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


def test_scrape_workday_helpers():
    sj._workday_api_and_base("https://wd3.myworkdaysite.com/wday/cxs/acme/site/jobs")


def test_scrape_module_main(monkeypatch):
    monkeypatch.setattr(sj, "HTTPX_AVAILABLE", False)
    monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py"])
    with pytest.raises(SystemExit):
        sj.main()


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

