"""Unit tests for scrape_jobs helpers, URL extractors, and edge cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from relocation_jobs.scrape_jobs import (
    _collect_listing_job_links,
    _detect_applytojob_from_url,
    _detect_ats_from_careers_url,
    _detect_bamboohr_from_url,
    _detect_deel_from_url,
    _detect_hirehive_from_url,
    _detect_join_from_url,
    _detect_recruitee_board_url,
    _detect_recruitee_from_careers_host,
    _detect_smartrecruiters_from_careers_url,
    _detect_teamtailor_from_url,
    _detect_workday_from_url,
    _extract_ashby,
    _extract_greenhouse,
    _extract_greenhouse_eu,
    _extract_lever,
    _extract_personio,
    _extract_recruitee,
    _extract_smartrecruiters,
    _extract_teamtailor,
    _extract_workable,
    _extract_workday,
    _filter_relevant_jobs,
    _html_to_text,
    _join_jobs_from_items,
    _jobs_from_bol_response,
    _jobs_from_job_shop_response,
    _jobs_from_listing_html,
    _listing_job,
    _normalize_title,
    _parse_deel_jobs,
    _parse_join_next_data,
    _parse_job_shop_config,
    _resolve_nuxt_payload_node,
    _smartrecruiters_api_url,
    _smartrecruiters_company_id,
    _bamboohr_location_text,
    _smartrecruiters_location_text,
    _teamtailor_location_map,
    _workable_location_text,
    _workday_api_and_base,
    detect_visa_relocation,
    fetch_job_description,
    guess_ats_url_from_name,
    is_relevant,
    merge_matching_jobs,
    today,
    now_iso,
)
from tests.helpers.http_mock import (
    MockResponse,
    install_requests_mock,
    json_response,
    load_ats_fixture,
    text_response,
)

FIXTURES_ATS = Path(__file__).parent / "fixtures" / "ats"


class TestUtilityFunctions:
    def test_today_iso_format(self):
        assert len(today()) == 10
        assert today()[4] == "-"

    def test_now_iso_utc(self):
        assert now_iso().endswith("+00:00")

    def test_listing_job_with_location(self):
        job = _listing_job("Backend Engineer", "https://example.com/j/1", location="Berlin")
        assert job["location"] == "Berlin"
        assert "locations" not in job

    def test_normalize_title_collapses_whitespace(self):
        assert _normalize_title("  Backend   Engineer  ") == "Backend Engineer"


class TestIsRelevantExtended:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Staff Software Engineer", False),
            ("Senior / Staff Product Engineer", True),
            ("Junior Backend Developer", False),
            ("DevOps Engineer", False),
            ("Site Reliability Engineer", False),
            ("AI Platform Engineer", False),
            ("AI Platform Software Engineer", True),
            ("Lead Backend Engineer", False),
            ("Engineering Manager", False),
            ("Principal Backend Engineer", False),
            ("Kotlin Backend Developer", True),
            ("Fullstack Engineer", True),
        ],
    )
    def test_relevance_edge_cases(self, title, expected):
        assert is_relevant(title) is expected


class TestFilterRelevantJobs:
    def test_drops_empty_title_or_url(self):
        jobs = [
            {"title": "", "url": "https://example.com/j/1"},
            {"title": "Backend Engineer", "url": ""},
            {"title": "Backend Engineer", "url": "https://example.com/j/2"},
        ]
        out = _filter_relevant_jobs(jobs, relevant_only=True)
        assert len(out) == 1
        assert out[0]["url"] == "https://example.com/j/2"

    def test_relevant_only_filters_titles(self):
        jobs = [
            {"title": "Backend Engineer", "url": "https://example.com/j/1"},
            {"title": "Marketing Manager", "url": "https://example.com/j/2"},
        ]
        out = _filter_relevant_jobs(jobs, relevant_only=True)
        assert len(out) == 1

    def test_not_relevant_only_keeps_all_valid(self):
        jobs = [
            {"title": "Backend Engineer", "url": "https://example.com/j/1", "location": "Berlin"},
            {"title": "Marketing Manager", "url": "https://example.com/j/2"},
        ]
        out = _filter_relevant_jobs(jobs, relevant_only=False)
        assert len(out) == 2
        assert out[0]["location"] == "Berlin"


class TestMergeMatchingJobsExtended:
    def test_merges_visa_from_scrape_when_missing(self):
        existing = [{"title": "Old", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"}]
        scraped = [{"title": "New Title", "url": "https://example.com/j/1?gh_jid=1", "visa_sponsorship": True}]
        merged, preserved, new_count, stale = merge_matching_jobs(existing, scraped)
        assert preserved == 1
        assert merged[0]["visa_sponsorship"] is True
        assert merged[0]["title"] == "New Title"

    def test_preserves_applied_and_rejected_flags(self):
        existing = [{
            "title": "Role",
            "url": "https://example.com/j/1?gh_jid=1",
            "fetched": "2025-01-01",
            "applied": True,
            "applied_date": "2025-02-01",
            "rejected": True,
            "rejected_date": "2025-03-01",
            "not_for_me": True,
            "not_for_me_date": "2025-04-01",
        }]
        scraped = [{"title": "Role", "url": "https://example.com/j/1?gh_jid=1"}]
        merged, _, _, _ = merge_matching_jobs(existing, scraped)
        job = merged[0]
        assert job["applied"] is True
        assert job["rejected"] is True
        assert job["not_for_me"] is True

    def test_preserves_listing_location_on_merge(self):
        existing = [{
            "title": "Backend Engineer",
            "url": "https://example.com/j/1?gh_jid=1",
            "fetched": "2025-01-01",
            "location": "Berlin, Germany",
        }]
        scraped = [{
            "title": "Backend Engineer",
            "url": "https://example.com/j/1?gh_jid=1",
            "location": "Munich, Germany",
        }]
        merged, preserved, _, _ = merge_matching_jobs(existing, scraped)
        assert preserved == 1
        assert merged[0]["location"] == "Munich, Germany"

        rescrape_without_loc = [{
            "title": "Backend Engineer",
            "url": "https://example.com/j/1?gh_jid=1",
        }]
        merged2, _, _, _ = merge_matching_jobs(existing, rescrape_without_loc)
        assert merged2[0]["location"] == "Berlin, Germany"

    def test_backfill_listing_locations_on_stale_kept(self):
        from relocation_jobs.scrape_jobs import backfill_listing_locations

        existing = [{
            "title": "Senior Solution Architect (f/m/d)",
            "url": "https://jobs.ashbyhq.com/adjoe/23feb94f-e60e-47aa-8ebf-26db8704a2c7",
            "fetched": "2025-01-01",
        }]
        title_matched = [{
            "title": "Senior Solution Architect (f/m/d)",
            "url": existing[0]["url"],
            "location": "Boston",
        }]
        merged, _, _, stale_kept = merge_matching_jobs(existing, [])
        assert stale_kept == 1
        assert "location" not in merged[0]

        backfill_listing_locations(merged, title_matched)
        assert merged[0]["location"] == "Boston"

    def test_deduplicates_existing_by_earliest_fetched(self):
        existing = [
            {"title": "A", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-02-01"},
            {"title": "B", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"},
        ]
        scraped = [{"title": "C", "url": "https://example.com/j/2?gh_jid=2"}]
        merged, _, new_count, _ = merge_matching_jobs(existing, scraped)
        assert new_count == 1
        preserved = [j for j in merged if "j/1" in j["url"]][0]
        assert preserved["fetched"] == "2025-01-01"


class TestDetectVisaRelocation:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("We offer visa sponsorship for qualified candidates.", True),
            ("Relocation package includes flight tickets.", True),
            ("Must already have the right to work in the EU.", False),
            ("Candidates must be eligible to work without sponsorship.", False),
            ("", None),
        ],
    )
    def test_detect_visa_relocation(self, text, expected):
        assert detect_visa_relocation(text) is expected

    def test_html_to_text(self):
        assert "backend engineer" in _html_to_text("<h1>Backend Engineer</h1><p>Python</p>")


class TestUrlExtractors:
    def test_extract_personio(self):
        url = "https://acme.jobs.personio.de/api/careers/jobs"
        assert "personio" in _extract_personio(url)

    def test_extract_lever_us_and_eu(self):
        assert _extract_lever("https://api.lever.co/v0/postings/acme") == "https://jobs.lever.co/acme"
        assert _extract_lever("https://api.eu.lever.co/v0/postings/acme") == "https://jobs.eu.lever.co/acme"

    def test_extract_greenhouse_embed(self):
        url = "https://boards.greenhouse.io/embed/job_board/js?for=acme"
        assert _extract_greenhouse(url) == "https://boards.greenhouse.io/acme"

    def test_extract_greenhouse_eu(self):
        url = "https://boards-api.eu.greenhouse.io/v1/boards/acme/jobs"
        assert _extract_greenhouse_eu(url) == "https://boards.eu.greenhouse.io/acme"

    def test_extract_ashby(self):
        assert "acme" in _extract_ashby("https://api.ashbyhq.com/posting-api/job-board/acme")

    def test_extract_workable(self):
        assert _extract_workable("https://apply.workable.com/api/v3/accounts/acme/jobs") == "https://apply.workable.com/acme/"

    def test_extract_recruitee_skips_proxy(self):
        assert _extract_recruitee("https://careers-analytics.recruitee.com/api/") == (
            "https://careers-analytics.recruitee.com/api/"
        )

    def test_extract_smartrecruiters(self):
        url = "https://api.smartrecruiters.com/v1/companies/AcmeCorp/postings"
        assert _smartrecruiters_company_id(url) == "AcmeCorp"
        assert _extract_smartrecruiters(url) == _smartrecruiters_api_url("AcmeCorp")

    def test_extract_teamtailor(self):
        ats_type, key = _extract_teamtailor(
            "https://api.teamtailor.com/v1/jobs?api_key=secret123",
            {"authorization": "Token token=abc"},
        )
        assert ats_type == "teamtailor"
        assert key == "abc"

    def test_extract_workday(self):
        api = "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs"
        result = _extract_workday(api)
        assert "|" in result


class TestDetectFromUrl:
    @pytest.mark.parametrize(
        "detector,url,expected_type",
        [
            (_detect_deel_from_url, "https://jobs.deel.com/acme", "deel"),
            (_detect_join_from_url, "https://join.com/companies/acme", "join"),
            (_detect_applytojob_from_url, "https://acme.applytojob.com/", "applytojob"),
            (_detect_bamboohr_from_url, "https://acme.bamboohr.com/careers", "bamboohr"),
            (_detect_smartrecruiters_from_careers_url, "https://careers.smartrecruiters.com/Acme", "smartrecruiters"),
            (_detect_recruitee_board_url, "https://acme.recruitee.com/", "recruitee"),
            (_detect_recruitee_from_careers_host, "https://careers.acme.com/jobs", "recruitee"),
            (_detect_teamtailor_from_url, "https://acme.teamtailor.com/jobs", "teamtailor"),
            (_detect_hirehive_from_url, "https://acme.hirehive.com", "hirehive"),
        ],
    )
    def test_url_detectors(self, detector, url, expected_type):
        ats_type, ats_url = detector(url)
        assert ats_type == expected_type
        assert ats_url

    def test_detect_workday_from_url(self):
        url = "https://acme.wd3.myworkdayjobs.com/en-US/careers"
        ats_type, ats_url = _detect_workday_from_url(url)
        assert ats_type == "workday"
        assert "wday/cxs" in ats_url

    def test_detect_ats_from_careers_url_chain(self):
        ats_type, _ = _detect_ats_from_careers_url("https://careers.smartrecruiters.com/Acme")
        assert ats_type == "smartrecruiters"


class TestWorkdayAndLocationHelpers:
    def test_workday_api_and_base(self):
        api = "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|https://acme.wd3.myworkdayjobs.com/en-US/careers"
        parsed_api, base = _workday_api_and_base(api)
        assert "wday/cxs" in parsed_api
        assert base.endswith("/careers")

    def test_workable_location_text(self):
        assert _workable_location_text({"city": "Berlin", "country": "Germany"}) == "Berlin, Germany"
        assert _workable_location_text(None) == ""

    def test_smartrecruiters_location_text(self):
        assert _smartrecruiters_location_text({"fullLocation": "Berlin, Germany"}) == "Berlin, Germany"

    def test_bamboohr_location_text(self):
        row = {
            "location": {"city": "Frankfurt am Main", "state": None, "addressCountry": "Germany"},
            "atsLocation": {"city": None, "country": None},
        }
        assert _bamboohr_location_text(row) == "Frankfurt am Main, Germany"
        assert _bamboohr_location_text({"isRemote": True}) == "Remote"
        assert _bamboohr_location_text({}) == ""


class TestParseHelpers:
    def test_parse_deel_jobs(self):
        html = load_ats_fixture("deel.html")
        jobs = _parse_deel_jobs(html, "acme", relevant_only=True)
        assert any("Backend" in j["title"] for j in jobs)

    def test_parse_join_next_data(self):
        data = load_ats_fixture("join_next_data.json")
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        slug, company_id, items = _parse_join_next_data(html)
        assert slug == "acme-corp"
        assert company_id == 4242
        assert len(items) == 2

    def test_join_jobs_from_items(self):
        items = [{"title": "Backend Engineer", "idParam": "backend-1"}]
        jobs = _join_jobs_from_items(items, "acme", relevant_only=True)
        assert jobs[0]["url"] == "https://join.com/companies/acme/backend-1"

    def test_jobs_from_bol_response(self):
        data = load_ats_fixture("bol.json")
        jobs = _jobs_from_bol_response(data)
        assert jobs[0]["title"] == "Backend Engineer"

    def test_jobs_from_job_shop_response(self):
        data = load_ats_fixture("job_shop.json")
        jobs = _jobs_from_job_shop_response(data, relevant_only=True)
        assert len(jobs) == 1

    def test_parse_job_shop_config(self):
        html = load_ats_fixture("job_shop_page.html")
        config = _parse_job_shop_config(html, "https://careers.acme.example.com/search")
        assert config is not None
        api_key, tenant_id, vanity = config
        assert len(api_key) > 20
        assert tenant_id == "acme"
        assert vanity == "vanity1"

    def test_resolve_nuxt_payload_node(self):
        payload = json.loads(
            (FIXTURES_ATS / "job_shop_page.html").read_text(encoding="utf-8")
            .split("__NUXT_DATA__")[1]
            .split("</script>")[0]
            .split(">", 1)[1]
        )
        root = _resolve_nuxt_payload_node(payload, 1)
        assert isinstance(root, dict)

    def test_teamtailor_location_map(self):
        included = load_ats_fixture("teamtailor.json")["included"]
        loc_map = _teamtailor_location_map(included)
        assert "loc1" in loc_map


class TestListingHtml:
    def test_jobs_from_listing_html(self, monkeypatch):
        html = """
        <html><body>
          <a href="/jobs/backend-engineer">Backend Engineer</a>
          <a href="/jobs/show_more">Show 10 more</a>
        </body></html>
        """
        install_requests_mock(monkeypatch, default_get=text_response(""))
        jobs = _jobs_from_listing_html(html, "https://example.com/careers", relevant_only=True)
        assert len(jobs) >= 1

    def test_collect_listing_job_links(self):
        from bs4 import BeautifulSoup

        html = '<a href="/jobs/backend-dev">Backend Developer</a>'
        soup = BeautifulSoup(html, "html.parser")
        links = _collect_listing_job_links(soup, "https://example.com/careers")
        assert any("Backend" in t for t in links.values())


class TestFetchJobDescription:
    def test_fetch_greenhouse_job_text(self, monkeypatch):
        detail = load_ats_fixture("greenhouse_job_detail.json")
        install_requests_mock(
            monkeypatch,
            get_routes={
                "boards-api.greenhouse.io": json_response(detail),
            },
        )
        text = fetch_job_description(
            "https://boards.greenhouse.io/acme/jobs/123456",
            "greenhouse",
        )
        assert "visa sponsorship" in text

    def test_fetch_lever_job_text(self, monkeypatch):
        detail = load_ats_fixture("lever_job_detail.json")
        install_requests_mock(
            monkeypatch,
            get_routes={"api.lever.co": json_response(detail)},
        )
        text = fetch_job_description(
            "https://jobs.lever.co/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "lever",
        )
        assert "relocation" in text.lower() or "no relocation" in text.lower()

    def test_fetch_recruitee_job_text(self, monkeypatch):
        offers = load_ats_fixture("recruitee.json")
        detail = load_ats_fixture("recruitee_offer_detail.json")

        def route(url, **kwargs):
            if url.endswith("/api/offers/"):
                return json_response(offers)
            if "/api/offers/101" in url:
                return json_response(detail)
            return MockResponse(status_code=404)

        install_requests_mock(monkeypatch, get_routes={"recruitee.com": route})
        text = fetch_job_description(
            "https://acme.recruitee.com/o/backend-developer",
            "recruitee",
        )
        assert "relocation" in text.lower() or "visa" in text.lower()

    def test_fetch_generic_html_fallback(self, monkeypatch):
        html = "<html><body>" + ("word " * 100) + "visa sponsorship</body></html>"
        install_requests_mock(
            monkeypatch,
            get_routes={"example.com": text_response(html)},
        )
        text = fetch_job_description("https://example.com/jobs/1", None)
        assert "visa sponsorship" in text


class TestGuessAtsUrl:
    def test_guess_ats_url_from_name(self):
        url = guess_ats_url_from_name("greenhouse", "Hello Fresh")
        assert "greenhouse.io" in url

    def test_guess_unknown_type_returns_empty(self):
        assert guess_ats_url_from_name("unknown_ats", "Acme") == ""
