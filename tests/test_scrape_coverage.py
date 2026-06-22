"""Additional targeted tests to cover remaining scrape_jobs branches."""

from __future__ import annotations

import json
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
        monkeypatch.setattr(sj, "load_country", lambda k: country_data)
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

