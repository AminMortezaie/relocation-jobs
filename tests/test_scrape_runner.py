"""Runner, progress/cancel reporters, enrich_jobs, and run_file tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from relocation_jobs import scrape_jobs as sj
from tests.helpers.http_mock import install_requests_mock, text_response

FIXTURES = Path(__file__).parent / "fixtures"


class TestCancelAndProgress:
    def test_cancel_checker(self):
        sj.set_cancel_checker(lambda: True)
        try:
            assert sj.is_cancel_requested() is True
            with pytest.raises(sj.FetchCancelled):
                sj.raise_if_cancelled()
        finally:
            sj.clear_cancel_checker()
        assert sj.is_cancel_requested() is False

    def test_progress_reporter(self, monkeypatch):
        events = []
        sj.set_progress_reporter(events.append)
        try:
            sj._report_progress(current=1, total=5, company="Acme", status="fetching", new_jobs=2)
            assert events[0]["current"] == 1
            assert events[0]["new_jobs"] == 2
        finally:
            sj.clear_progress_reporter()

    def test_review_reporter(self):
        events = []
        sj.set_review_reporter(events.append)
        try:
            sj._report_review_jobs(
                included=[{"title": "Backend Engineer", "url": "https://example.com/j/1"}],
                filtered=[{
                    "title": "Marketing",
                    "url": "https://example.com/j/2",
                    "filter_reason": "Title excluded (marketing)",
                }],
            )
            assert len(events[0]["included"]) == 1
            assert len(events[0]["filtered"]) == 1
            assert events[0]["filtered"][0]["filter_reason"] == "Title excluded (marketing)"
        finally:
            sj.clear_review_reporter()

    def test_emit_panel_ipc_when_child(self, monkeypatch, capsys):
        monkeypatch.setenv("PANEL_SCRAPE_CHILD", "1")
        sj._report_activity("Loading jobs", detail="Acme")
        out = capsys.readouterr().out
        assert "@@ACTIVITY@@" in out

    def test_review_entry_filters_noise(self):
        assert sj._review_entry({"title": "Show 10 more", "url": "https://example.com/jobs/show_more"}) is None
        entry = sj._review_entry({"title": "Backend Engineer", "url": "https://example.com/j/1"})
        assert entry["title"] == "Backend Engineer"


class TestEnrichJobs:
    def test_enrich_one_job_sync(self, monkeypatch):
        monkeypatch.setattr(
            sj,
            "fetch_job_description",
            lambda url, ats_type=None: "visa sponsorship available",
        )
        job = {"title": "Backend Engineer", "url": "https://example.com/j/1"}
        sj._enrich_one_job(job, "greenhouse", "2025-06-01", only_missing=False)
        assert job["visa_sponsorship"] is True
        assert job["fetched"] == "2025-06-01"

    def test_enrich_jobs_without_httpx(self, monkeypatch):
        monkeypatch.setattr(sj, "HTTPX_AVAILABLE", False)
        monkeypatch.setattr(
            sj,
            "fetch_job_description",
            lambda url, ats_type=None: "no relocation",
        )
        jobs = [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]
        company = {"ats_type": None}
        out = sj.enrich_jobs(jobs, company)
        assert out[0]["visa_sponsorship"] is False

    def test_enrich_jobs_with_httpx(self, monkeypatch):
        async def fake_enrich(client, jobs, company, **kwargs):
            for job in jobs:
                job["visa_sponsorship"] = True
            return jobs

        monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
        monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)
        jobs = [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]
        out = sj.enrich_jobs(jobs, {"ats_type": None})
        assert out[0]["visa_sponsorship"] is True


class TestDetectAtsForHint:
    def test_detect_ats_for_hint_from_url(self):
        ats_type, ats_url = sj.detect_ats_for_hint(
            "Acme",
            "https://acme.recruitee.com/",
            "recruitee",
        )
        assert ats_type == "recruitee"
        assert "recruitee.com" in ats_url

    def test_detect_ats_for_hint_careers_page_ats(self):
        ats_type, ats_url = sj.detect_ats_for_hint(
            "EPAM",
            "https://careers.epam.com/",
            "epam",
        )
        assert ats_type == "epam"
        assert ats_url.startswith("https://careers.epam.com")

    def test_detect_ats_for_hint_auto_returns_empty(self):
        assert sj.detect_ats_for_hint("Acme", "https://example.com", "auto") == ("", "")


class TestRunFile:
    def test_run_file_async_single_company(self, monkeypatch):
        country_data = {
            "companies": [
                {
                    "name": "Acme",
                    "city": "Berlin",
                    "careers_url": "https://example.com/careers",
                    "matching_jobs": [],
                }
            ]
        }

        monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
        monkeypatch.setattr(sj, "load_country", lambda k: country_data)
        monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
        monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)

        async def fake_get_jobs(client, company, **kwargs):
            return [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]

        monkeypatch.setattr(sj, "get_jobs_async", fake_get_jobs)

        async def fake_enrich(client, jobs, company, **kwargs):
            for j in jobs:
                j.setdefault("visa_sponsorship", False)
            return jobs

        monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)

        asyncio.run(
            sj.run_file_async("test", target="Acme", concurrency=1)
        )
        assert country_data["companies"][0].get("fetch_ok") is True
        assert len(country_data["companies"][0]["matching_jobs"]) >= 1

    def test_run_file_async_enrich_only(self, monkeypatch):
        country_data = {
            "companies": [
                {
                    "name": "Acme",
                    "city": "Berlin",
                    "careers_url": "https://example.com/careers",
                    "matching_jobs": [
                        {"title": "Backend Engineer", "url": "https://example.com/j/1"}
                    ],
                }
            ]
        }

        monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
        monkeypatch.setattr(sj, "load_country", lambda k: country_data)
        monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
        monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)

        async def fake_enrich(client, jobs, company, **kwargs):
            for j in jobs:
                j["visa_sponsorship"] = True
            return jobs

        monkeypatch.setattr(sj, "enrich_jobs_async_with_client", fake_enrich)
        get_jobs_mock = AsyncMock()
        monkeypatch.setattr(sj, "get_jobs_async", get_jobs_mock)

        asyncio.run(
            sj.run_file_async("test", target="Acme", enrich_only=True, concurrency=1)
        )
        get_jobs_mock.assert_not_called()
        assert country_data["companies"][0]["matching_jobs"][0]["visa_sponsorship"] is True

    def test_run_country_wrapper(self, monkeypatch):
        called = {}

        async def fake_run_file_async(*args, **kwargs):
            called["args"] = args
            called["kwargs"] = kwargs

        monkeypatch.setattr(sj, "run_file_async", fake_run_file_async)
        sj.run_country("uk", target="Acme", workers=4)
        assert called["kwargs"]["concurrency"] == 4

    def test_run_file_missing_company_raises(self, monkeypatch):
        monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
        monkeypatch.setattr(sj, "load_country", lambda k: {"companies": []})
        with pytest.raises(LookupError):
            asyncio.run(sj.run_file_async("test", target="MissingCo"))


class TestProcessCompanyAsync:
    @pytest.mark.asyncio
    async def test_process_company_handles_error(self, monkeypatch):
        client = httpx.AsyncClient()
        company = {
            "name": "Broken",
            "city": "Berlin",
            "careers_url": "https://example.com/careers",
            "matching_jobs": [],
        }

        async def boom(*args, **kwargs):
            raise RuntimeError("scrape failed")

        monkeypatch.setattr(sj, "get_jobs_async", boom)
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
        assert "Error" in msg
        assert new_count == 0
        await client.aclose()
