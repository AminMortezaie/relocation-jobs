"""Parametrized sync ATS scraper tests with mocked HTTP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from relocation_jobs import scrape_jobs as sj
from tests.helpers.http_mock import install_requests_mock, json_response, load_ats_fixture, text_response

FIXTURES_ATS = Path(__file__).parent / "fixtures" / "ats"


def _join_html(data: dict) -> str:
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


@pytest.fixture
def mock_pw(monkeypatch):
    from tests.helpers.playwright_mock import install_playwright_mock

    return install_playwright_mock(monkeypatch, available=False)


class TestScrapeAshby:
    @pytest.mark.network
    def test_scrape_ashby(self, monkeypatch, mock_pw):
        payload = load_ats_fixture("ashby.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"api.ashbyhq.com": json_response(payload)},
        )
        jobs = sj.scrape_ashby("https://jobs.ashbyhq.com/acme")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeWorkable:
    @pytest.mark.network
    def test_scrape_workable(self, monkeypatch):
        payload = load_ats_fixture("workable.json")
        install_requests_mock(
            monkeypatch,
            post_routes={"apply.workable.com": json_response(payload)},
        )
        jobs = sj.scrape_workable("https://apply.workable.com/acme/")
        assert jobs[0]["title"] == "Backend Software Engineer"


class TestScrapeRecruitee:
    @pytest.mark.network
    def test_scrape_recruitee(self, monkeypatch):
        payload = load_ats_fixture("recruitee.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"recruitee.com/api/offers": json_response(payload)},
        )
        jobs = sj.scrape_recruitee("https://acme.recruitee.com/")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeSmartrecruiters:
    @pytest.mark.network
    def test_scrape_smartrecruiters(self, monkeypatch):
        payload = load_ats_fixture("smartrecruiters.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"api.smartrecruiters.com": json_response(payload)},
        )
        jobs = sj.scrape_smartrecruiters(
            "https://api.smartrecruiters.com/v1/companies/Acme/postings"
        )
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapePersonio:
    @pytest.mark.network
    def test_scrape_personio_com_api(self, monkeypatch):
        payload = load_ats_fixture("personio.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"personio.com/api/careers/jobs": json_response(payload)},
        )
        jobs = sj.scrape_personio("https://www.personio.com/api/careers/jobs/list")
        assert any("Software Engineer" in j["title"] for j in jobs)

    @pytest.mark.network
    def test_scrape_personio_xml(self, monkeypatch):
        xml = load_ats_fixture("personio.xml")
        install_requests_mock(
            monkeypatch,
            get_routes={
                "jobs.personio.de/xml": text_response(xml),
            },
        )
        jobs = sj.scrape_personio("https://acme.jobs.personio.de/")
        assert any("Platform Engineer" in j["title"] for j in jobs)


class TestScrapeWorkday:
    @pytest.mark.network
    def test_scrape_workday(self, monkeypatch):
        payload = load_ats_fixture("workday.json")
        ats_url = (
            "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|"
            "https://acme.wd3.myworkdayjobs.com/en-US/careers"
        )
        install_requests_mock(
            monkeypatch,
            post_routes={"myworkdayjobs.com": json_response(payload)},
        )
        jobs = sj.scrape_workday(ats_url)
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeBamboohr:
    @pytest.mark.network
    def test_scrape_bamboohr(self, monkeypatch):
        payload = load_ats_fixture("bamboohr.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"bamboohr.com": json_response(payload)},
        )
        jobs = sj.scrape_bamboohr("https://acme.bamboohr.com/careers/list")
        assert jobs[0]["title"] == "Backend Engineer"
        assert jobs[0]["location"] == "Frankfurt am Main, Germany"


class TestScrapeTeamtailor:
    @pytest.mark.network
    def test_scrape_teamtailor_api(self, monkeypatch, mock_pw):
        payload = load_ats_fixture("teamtailor.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"api.teamtailor.com": json_response(payload)},
        )
        jobs = sj.scrape_teamtailor(
            "test-api-key",
            "https://acme.teamtailor.com/jobs",
        )
        assert any("Software Engineer" in j["title"] for j in jobs)


class TestScrapeBol:
    @pytest.mark.network
    def test_scrape_bol(self, monkeypatch):
        payload = load_ats_fixture("bol.json")
        install_requests_mock(
            monkeypatch,
            post_routes={"careers.bol.com": json_response(payload)},
        )
        jobs = sj.scrape_bol("https://careers.bol.com/en/jobs/")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeJobShop:
    @pytest.mark.network
    def test_scrape_job_shop(self, monkeypatch):
        page_html = load_ats_fixture("job_shop_page.html")
        search_payload = load_ats_fixture("job_shop.json")

        def get_route(url, **kwargs):
            if "careers.acme" in url:
                return text_response(page_html)
            return text_response("", status_code=404)

        install_requests_mock(
            monkeypatch,
            get_routes={"careers.acme": get_route},
            post_routes={"api.my-job-shop.com": json_response(search_payload)},
        )
        jobs = sj.scrape_job_shop("https://careers.acme.example.com/")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeDeel:
    @pytest.mark.network
    def test_scrape_deel(self, monkeypatch):
        html = load_ats_fixture("deel.html")
        install_requests_mock(
            monkeypatch,
            get_routes={"jobs.deel.com": text_response(html)},
        )
        jobs = sj.scrape_deel("https://jobs.deel.com/acme")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeJoin:
    @pytest.mark.network
    def test_scrape_join(self, monkeypatch):
        next_data = load_ats_fixture("join_next_data.json")
        api_data = load_ats_fixture("join_api.json")

        def get_route(url, **kwargs):
            if "join.com/companies" in url and "/jobs" not in url.split("companies/")[1]:
                return text_response(_join_html(next_data))
            if "/api/public/companies/" in url:
                return json_response(api_data)
            return text_response("", status_code=404)

        install_requests_mock(monkeypatch, get_routes={"join.com": get_route})
        jobs = sj.scrape_join("https://join.com/companies/acme-corp")
        assert any("Backend" in j["title"] or "Golang" in j["title"] for j in jobs)


class TestScrapeApplytojob:
    @pytest.mark.network
    def test_scrape_applytojob(self, monkeypatch):
        html = load_ats_fixture("applytojob.html")
        install_requests_mock(
            monkeypatch,
            get_routes={"applytojob.com": text_response(html)},
        )
        jobs = sj.scrape_applytojob("https://acme.applytojob.com/")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeEpam:
    @pytest.mark.network
    def test_scrape_epam(self, monkeypatch):
        html = load_ats_fixture("epam.html")
        install_requests_mock(
            monkeypatch,
            get_routes={"careers.epam.com": text_response(html)},
        )
        jobs = sj.scrape_epam("https://careers.epam.com/")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeHirehive:
    @pytest.mark.network
    def test_scrape_hirehive(self, monkeypatch):
        payload = load_ats_fixture("hirehive.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"hirehive.com": json_response(payload)},
        )
        jobs = sj.scrape_hirehive("https://acme.hirehive.com")
        assert any("Software Engineer" in j["title"] for j in jobs)


class TestScrapeRss:
    @pytest.mark.network
    def test_scrape_rss(self, monkeypatch):
        xml = load_ats_fixture("rss.xml")
        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": text_response(xml)},
        )
        jobs = sj.scrape_rss("https://example.com/feed.xml")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeMovingimage:
    @pytest.mark.network
    def test_scrape_movingimage(self, monkeypatch):
        listing = load_ats_fixture("movingimage.html")
        detail = load_ats_fixture("movingimage_job.html")

        def get_route(url, **kwargs):
            if url.endswith("/careers/backend-engineer"):
                return text_response(detail)
            return text_response(listing)

        install_requests_mock(monkeypatch, get_routes={"movingimage.com": get_route})
        jobs = sj.scrape_movingimage("https://www.movingimage.com/careers")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeProjectA:
    @pytest.mark.network
    def test_scrape_project_a(self, monkeypatch):
        listing = load_ats_fixture("project_a.html")
        detail = load_ats_fixture("project_a_job.html")

        def get_route(url, **kwargs):
            if "/careers/123456" in url:
                return text_response(detail)
            return text_response(listing)

        install_requests_mock(monkeypatch, get_routes={"project-a.vc": get_route})
        jobs = sj.scrape_project_a("https://www.project-a.vc/careers")
        assert any("Platform Engineer" in j["title"] for j in jobs)


class TestScrapeGeneric:
    @pytest.mark.network
    def test_scrape_generic(self, monkeypatch):
        html = '<html><body><a href="/jobs/backend-dev">Backend Developer</a></body></html>'
        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": text_response(html)},
            default_get=text_response(""),
        )
        jobs = sj.scrape_generic("https://example.com/careers")
        assert len(jobs) >= 1
