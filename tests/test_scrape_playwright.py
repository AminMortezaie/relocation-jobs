"""Playwright-based scrape paths with mocked sync_playwright."""

from __future__ import annotations

import pytest

from relocation_jobs import scrape_jobs as sj
from tests.helpers.playwright_mock import MockPlaywrightPage, install_playwright_mock


@pytest.fixture
def pw_page():
    return MockPlaywrightPage()


@pytest.fixture
def pw_enabled(monkeypatch, pw_page):
    return install_playwright_mock(monkeypatch, page=pw_page, available=True)


class TestDetectAtsViaPlaywright:
    def test_detects_xhr_greenhouse(self, pw_enabled, pw_page):
        pw_page._request_urls = [
            (
                "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
                {},
            )
        ]
        ats_type, ats_url = sj.detect_ats_via_playwright("https://example.com/careers")
        assert ats_type == "greenhouse"
        assert "acme" in ats_url

    def test_detects_html_fallback_lever(self, pw_enabled, pw_page):
        pw_page._html = "Apply at https://jobs.lever.co/acme today"
        ats_type, ats_url = sj.detect_ats_via_playwright("https://example.com/careers")
        assert ats_type == "lever"
        assert "acme" in ats_url

    def test_respects_ats_hint(self, pw_enabled, pw_page):
        pw_page._request_urls = [
            ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", {}),
            ("https://api.lever.co/v0/postings/other", {}),
        ]
        ats_type, ats_url = sj.detect_ats_via_playwright(
            "https://example.com/careers",
            ats_hint="lever",
        )
        assert ats_type == "lever"
        assert "lever" in ats_url

    def test_unavailable_playwright_returns_none(self, monkeypatch):
        install_playwright_mock(monkeypatch, available=False)
        assert sj.detect_ats_via_playwright("https://example.com/careers") == (None, None)


class TestScrapeWithPlaywright:
    def test_scrape_with_playwright_listing(self, pw_enabled, pw_page):
        pw_page._html = """
        <html><body>
          <a href="/jobs/backend-engineer">Backend Engineer</a>
        </body></html>
        """
        jobs = sj.scrape_with_playwright("https://example.com/careers")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeJibe:
    def test_scrape_jibe_pagination(self, pw_enabled, pw_page):
        pw_page._evaluate_results = [
            [
                {"h": "https://jobs.booking.com/booking/jobs/backend-1", "t": "Backend Engineer"},
            ],
            [],
        ]
        jobs = sj.scrape_jibe("https://jobs.booking.com/booking/jobs")
        assert any("Backend" in j["title"] for j in jobs)


class TestScrapeAtlassian:
    def test_scrape_atlassian(self, pw_enabled, pw_page):
        pw_page._evaluate_results = [[
            {
                "h": "https://www.atlassian.com/company/careers/details/123",
                "t": "Software Engineer Backend",
            }
        ]]
        jobs = sj.scrape_atlassian("https://www.atlassian.com/company/careers/all-jobs")
        assert any("Software Engineer" in j["title"] for j in jobs)


class TestScrapeGenericPlaywrightFallback:
    def test_ashby_api_failure_falls_back_to_playwright(self, monkeypatch, pw_enabled, pw_page):
        from tests.helpers.http_mock import install_requests_mock, MockResponse

        install_requests_mock(
            monkeypatch,
            get_routes={"api.ashbyhq.com": MockResponse(status_code=500, text="error")},
        )
        pw_page._html = '<html><body><a href="/jobs/backend">Backend Engineer</a></body></html>'
        jobs = sj.scrape_ashby("https://jobs.ashbyhq.com/acme")
        assert len(jobs) >= 1

    def test_fetch_job_description_playwright_fallback(self, monkeypatch, pw_enabled, pw_page):
        from tests.helpers.http_mock import install_requests_mock, MockResponse

        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": MockResponse(status_code=404, text="")},
        )
        pw_page._html = "<html><body>" + ("word " * 100) + "visa sponsorship</body></html>"
        text = sj.fetch_job_description("https://example.com/jobs/1")
        assert "visa sponsorship" in text


class TestPlaywrightCancellation:
    def test_raise_if_cancelled_during_pause(self, pw_enabled, pw_page, monkeypatch):
        sj.set_cancel_checker(lambda: True)
        try:
            with pytest.raises(sj.FetchCancelled):
                sj.detect_ats_via_playwright("https://example.com/careers")
        finally:
            sj.clear_cancel_checker()
