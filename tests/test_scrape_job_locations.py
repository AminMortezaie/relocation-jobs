"""Listing location extraction, backfill, and catalog persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from relocation_jobs import scrape_jobs as sj
from relocation_jobs.catalog_db import load_country, save_country
from relocation_jobs.panel_data import _job_dict
from relocation_jobs.scrape_jobs import backfill_listing_locations, merge_matching_jobs
from tests.helpers.http_mock import install_requests_mock, json_response, load_ats_fixture, text_response

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURES_ATS = FIXTURES / "ats"

SCRAPER_LOCATION_CASES = [
    (
        "greenhouse",
        lambda mp: _mock_greenhouse(mp),
        lambda: sj.scrape_greenhouse("https://boards.greenhouse.io/acmebackend"),
        "London",
    ),
    (
        "lever",
        lambda mp: _mock_lever(mp),
        lambda: sj.scrape_lever("https://jobs.lever.co/acme"),
        "Amsterdam",
    ),
    (
        "ashby",
        lambda mp: (
            mp.setattr(sj, "PLAYWRIGHT_AVAILABLE", False),
            install_requests_mock(
                mp,
                get_routes={"api.ashbyhq.com": json_response(load_ats_fixture("ashby.json"))},
            ),
        ),
        lambda: sj.scrape_ashby("https://jobs.ashbyhq.com/acme"),
        "Berlin",
    ),
    (
        "workable",
        lambda mp: install_requests_mock(
            mp,
            post_routes={"apply.workable.com": json_response(load_ats_fixture("workable.json"))},
        ),
        lambda: sj.scrape_workable("https://apply.workable.com/acme/"),
        "Amsterdam",
    ),
    (
        "smartrecruiters",
        lambda mp: install_requests_mock(
            mp,
            get_routes={"api.smartrecruiters.com": json_response(load_ats_fixture("smartrecruiters.json"))},
        ),
        lambda: sj.scrape_smartrecruiters(
            "https://api.smartrecruiters.com/v1/companies/Acme/postings"
        ),
        "Berlin",
    ),
    (
        "workday",
        lambda mp: install_requests_mock(
            mp,
            post_routes={"myworkdayjobs.com": json_response(load_ats_fixture("workday.json"))},
        ),
        lambda: sj.scrape_workday(
            "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|"
            "https://acme.wd3.myworkdayjobs.com/en-US/careers"
        ),
        "Amsterdam",
    ),
]


def _mock_greenhouse(monkeypatch):
    payload = json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))
    response = type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: payload})()
    monkeypatch.setattr(sj.requests, "get", lambda *args, **kwargs: response)


def _mock_lever(monkeypatch):
    payload = json.loads((FIXTURES / "lever_postings.json").read_text(encoding="utf-8"))
    response = type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: payload})()
    monkeypatch.setattr(sj.requests, "get", lambda *args, **kwargs: response)


@pytest.mark.parametrize("ats_name,install_mock,run_scraper,expected_city", SCRAPER_LOCATION_CASES)
@pytest.mark.network
def test_scraper_sets_listing_location(monkeypatch, ats_name, install_mock, run_scraper, expected_city):
    install_mock(monkeypatch)
    jobs = [j for j in run_scraper() if sj.is_relevant(j.get("title", ""))]
    assert jobs, f"{ats_name} returned no relevant jobs"
    located = [j for j in jobs if (j.get("location") or "").strip() or j.get("locations")]
    assert located, f"{ats_name} scrape omitted listing location: {jobs[0]}"
    if expected_city:
        assert expected_city.casefold() in (located[0].get("location") or "").casefold()


@pytest.mark.integration
def test_location_backfill_persists_through_catalog(db, sample_country_data):
    company = sample_country_data["companies"][0]
    stale = {
        "title": "Senior Backend Engineer",
        "url": "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456",
        "fetched": "2025-06-01",
        "last_seen": "2025-06-01",
    }
    company["matching_jobs"] = [stale]
    title_matched = [{
        "title": stale["title"],
        "url": stale["url"],
        "location": "London, UK",
    }]

    merged, _, _, stale_kept = merge_matching_jobs([stale], [])
    assert stale_kept == 1
    assert "location" not in merged[0]

    backfill_listing_locations(merged, title_matched)
    company["matching_jobs"] = merged
    save_country("uk", sample_country_data, export_archive=False)

    loaded = load_country("uk")
    stored = loaded["companies"][0]["matching_jobs"][0]
    assert stored["location"] == "London, UK"

    row = _job_dict(
        stored,
        company_name=company["name"],
        company=company,
        key="uk",
        label="United Kingdom",
    )
    assert row["job_city"] == "London"


@pytest.mark.integration
def test_api_job_dict_has_city_after_fetch_style_backfill(seeded_catalog):
    job = {
        "title": "Backend Engineer",
        "url": "https://jobs.ashbyhq.com/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "fetched": "2025-06-01",
        "location": "Hamburg",
    }
    company = seeded_catalog["companies"][0]
    row = _job_dict(
        job,
        company_name=company["name"],
        company=company,
        key="uk",
        label="United Kingdom",
    )
    assert row["location"] == "Hamburg"
    assert row["job_city"] == "Hamburg"


@pytest.mark.integration
def test_wrong_location_jobs_hidden_after_catalog_save(db, sample_country_data):
    from relocation_jobs.panel_data import flatten_companies

    company = sample_country_data["companies"][0]
    company["locations"] = [{"country": "uk", "city": "London"}]
    company["matching_jobs"] = [
        {"title": "Local", "url": "https://example.com/local", "location": "London, UK"},
        {"title": "Far", "url": "https://example.com/far", "location": "Tokyo, Japan"},
    ]
    save_country("uk", sample_country_data, export_archive=False)

    companies, _, _ = flatten_companies("uk")
    acme = companies[0]
    assert [j["url"] for j in acme["jobs"]] == ["https://example.com/local"]
    assert acme["not_for_me_jobs"][0]["not_for_me_reason"] == "wrong_location"
