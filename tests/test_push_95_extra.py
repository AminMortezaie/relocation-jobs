"""Additional panel_data and scrape coverage tests."""

from __future__ import annotations

import copy
import importlib
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from relocation_jobs.catalog_db import save_country
from tests.helpers.postgres_mock import FakePgConnection
from relocation_jobs.panel_data import (
    _normalize_linkedin_url,
    _resolve_status_history,
    _tracking_bool,
    add_company,
    flatten_companies,
    load_country_file,
    remove_company,
    rename_company,
    set_job_not_for_me,
    update_company_careers,
)
from relocation_jobs import scrape_jobs as sj
from tests.helpers.http_mock import install_requests_mock, json_response, text_response


@pytest.mark.integration
def test_normalize_linkedin_url_variants():
    assert _normalize_linkedin_url("linkedin.com/in/user") == "https://linkedin.com/in/user"
    with pytest.raises(ValueError):
        _normalize_linkedin_url("https://twitter.com/user")


@pytest.mark.integration
def test_tracking_bool_and_status_history_merge(db, seeded_catalog, test_user):
    from relocation_jobs.db import set_job_applied_db

    uid = test_user["id"]
    company = seeded_catalog["companies"][0]["name"]
    url = seeded_catalog["companies"][0]["matching_jobs"][0]["url"]
    set_job_applied_db(uid, "uk", company, url, True)

    history = {
        ("uk", company, url): {
            "applied": ["2025-01-01"],
            "rejected": [],
            "applied_events": [{"date": "2025-01-01", "at": "2025-01-01T12:00:00"}],
            "rejected_events": [],
        }
    }
    merged = _resolve_status_history(
        history,
        country="uk",
        company_name=company,
        job={"url": url},
    )
    assert merged["applied_events"]
    assert _tracking_bool("yes") is True
    assert _tracking_bool(None) is False


@pytest.mark.integration
def test_flatten_without_user_not_for_me_in_json(seeded_catalog, sample_country_data):
    data = copy.deepcopy(sample_country_data)
    data["companies"][0]["matching_jobs"][0]["not_for_me"] = True
    save_country("uk", data, export_archive=False)
    companies, _, _ = flatten_companies("uk", hide_applied=True, hide_empty=True, not_applied_only=True)
    assert isinstance(companies, list)


@pytest.mark.integration
def test_flatten_all_countries_and_location_filter(seeded_catalog, test_user):
    companies, meta, _ = flatten_companies(None, user_id=test_user["id"], location="uk:London")
    assert meta
    assert isinstance(companies, list)


@pytest.mark.integration
def test_company_crud_edge_cases(db, sample_country_data, monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.panel_data.fetch_relocate_metadata",
        lambda *a, **k: {"city": "London", "size": "51-200", "country": "uk"},
    )
    monkeypatch.setattr(
        "relocation_jobs.panel_data.detect_ats_for_company",
        lambda *a, **k: ("greenhouse", "https://boards.greenhouse.io/x"),
    )
    add_company("Edge Co", "https://boards.greenhouse.io/x", "uk")
    update_company_careers("uk", "Edge Co", "https://boards.greenhouse.io/x2", redetect_ats=False)
    rename_company("uk", "Edge Co", "Edge Renamed")
    remove_company("uk", "Edge Renamed")


@pytest.mark.integration
def test_set_job_not_for_me_panel(db, seeded_catalog, test_user):
    company = seeded_catalog["companies"][0]["name"]
    url = seeded_catalog["companies"][0]["matching_jobs"][0]["url"]
    result = set_job_not_for_me("uk", company, url, user_id=test_user["id"], not_for_me=True, reason="pay")
    assert result["not_for_me"] is True


@pytest.mark.integration
def test_load_country_file_fallback(tmp_path, sample_country_data):
    orphan = tmp_path / "orphan.json"
    orphan.write_text('{"companies": [], "total": 0}', encoding="utf-8")
    data = load_country_file(orphan)
    assert data["companies"] == []


@pytest.mark.network
def test_scrape_final_push_batch(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={"careers.epam.com": text_response("<html></html>")},
    )
    assert sj.scrape_epam("https://careers.epam.com/") == []
    assert sj.scrape_smartrecruiters("https://example.com/bad") == []


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

    def fake_run_file(*args, **kwargs):
        called.append(kwargs)

    monkeypatch.setattr(sj, "run_file", fake_run_file)
    monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--workers", "6"])
    sj.main()
    assert called[0]["workers"] == 6


def test_enrich_jobs_empty_list():
    assert sj.enrich_jobs([], {"ats_type": None}) == []


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


@pytest.mark.asyncio
@respx.mock
async def test_scrape_async_error_paths():
    client = httpx.AsyncClient()
    respx.get("https://join.com/companies/acme").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_join_async(client, "https://join.com/companies/acme") == []
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(500, text="err"))
    assert await sj.scrape_generic_async(client, "https://example.com/careers") == []
    assert await sj.detect_ats_static_async(client, "https://example.com/careers") == (None, None)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_scrape_smartrecruiters_async_no_company_id():
    client = httpx.AsyncClient()
    assert await sj.scrape_smartrecruiters_async(client, "https://example.com/bad") == []
    await client.aclose()


def test_playwright_detect_exception(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def broken_cm():
        raise RuntimeError("playwright boom")
        yield  # pragma: no cover

    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(sj, "sync_playwright", broken_cm)
    assert sj.detect_ats_via_playwright("https://example.com/careers") == (None, None)
    assert sj.scrape_with_playwright("https://example.com/careers") == []


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
        assert reviews
        filtered = reviews[0]["filtered"]
        assert len(filtered) == 1
        assert filtered[0]["filter_reason"].startswith("Title")
    finally:
        sj.clear_review_reporter()
        await client.aclose()


@pytest.mark.network
def test_apply_known_ats_override_with_save(monkeypatch):
    saved = []
    company = {
        "name": "HelloFresh",
        "careers_url": "https://careers.hellofresh.com",
        "ats_type": "generic",
        "ats_url": "",
    }
    sj._apply_known_ats_override(company, save_fn=lambda: saved.append(True))
    assert saved
    assert company["ats_type"] == sj.KNOWN_ATS["HelloFresh"][0]


def test_main_missing_workers_and_file_args(monkeypatch, capsys):
    monkeypatch.setattr(sj, "run_file", lambda *a, **k: None)
    monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--workers"])
    sj.main()
    assert "--workers requires" in capsys.readouterr().out
    monkeypatch.setattr(sj.sys, "argv", ["scrape_jobs.py", "--file"])
    sj.main()
    assert "--file requires" in capsys.readouterr().out


def test_review_entry_junk_title():
    assert sj._review_entry({"title": "Show 5 more", "url": "https://example.com/j/1"}) is None
    assert sj._review_entry({"title": "Backend Engineer", "url": "https://example.com/j/1"})


@pytest.mark.network
def test_build_companies_playwright_import_error(monkeypatch):
    mod = importlib.import_module("relocation_jobs.build_companies")
    real_import = __import__

    def block(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=block):
        reloaded = importlib.reload(mod)
        assert reloaded.PLAYWRIGHT_AVAILABLE is False
    importlib.reload(importlib.import_module("relocation_jobs.build_companies"))


@pytest.mark.integration
def test_panel_data_fetch_relocate_errors(monkeypatch):
    import requests
    from relocation_jobs.panel_data import fetch_relocate_metadata

    def boom(*a, **k):
        raise requests.RequestException("network")

    monkeypatch.setattr("relocation_jobs.panel_data.requests.get", boom)
    assert fetch_relocate_metadata("Missing Co", country_key="uk") == {}


@pytest.mark.integration
def test_panel_data_validation_errors(db):
    from relocation_jobs.panel_data import (
        add_manual_jobs,
        remove_company,
        rename_company,
        update_company_city,
    )

    with pytest.raises(ValueError):
        update_company_city("nope", "Co", cities=["London"])
    with pytest.raises(LookupError):
        update_company_city("uk", "Missing Co", cities=["London"])
    with pytest.raises(ValueError):
        add_manual_jobs("uk", "Co", [])
    with pytest.raises(ValueError):
        rename_company("uk", "", "New")
    with pytest.raises(ValueError):
        remove_company("uk", "")


@pytest.mark.asyncio
async def test_run_file_cancel_concurrent(monkeypatch):
    import asyncio

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
    json_path = "/tmp/fake.json"
    monkeypatch.setattr(sj, "HTTPX_AVAILABLE", True)
    monkeypatch.setattr(sj, "resolve_json_path", lambda p: json_path)
    monkeypatch.setattr(sj, "load_country_for_path", lambda p: ("test", data))
    monkeypatch.setattr(sj, "upsert_company", lambda *a, **k: None)
    monkeypatch.setattr(sj, "touch_country_meta", lambda *a, **k: None)
    monkeypatch.setattr(sj, "export_country_archive", lambda *a, **k: None)

    call_count = {"n": 0}

    async def slow_get_jobs(client, company, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            sj.set_cancel_checker(lambda: True)
        await asyncio.sleep(0.05)
        return [{"title": "Backend Engineer", "url": "https://example.com/j/1"}]

    monkeypatch.setattr(sj, "get_jobs_async", slow_get_jobs)
    monkeypatch.setattr(sj, "enrich_jobs_async_with_client", AsyncMock(side_effect=lambda c, j, co, **kw: j))
    try:
        await sj.run_file_async(json_path, concurrency=2)
    finally:
        sj.clear_cancel_checker()


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

    monkeypatch.setattr(sj, "get_jobs_async", fake_get_jobs)
    monkeypatch.setattr(sj, "enrich_jobs_async_with_client", AsyncMock(side_effect=lambda c, j, co, **kw: j))

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
def test_get_jobs_no_ats_persists_empty(monkeypatch):
    monkeypatch.setattr(sj, "detect_ats_static", lambda url: (None, None))
    monkeypatch.setattr(sj, "detect_ats_via_playwright", lambda url: (None, None))
    monkeypatch.setattr(sj, "scrape_generic", lambda url: [])
    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", False)
    company = {"name": "Co", "careers_url": "https://example.com/careers"}
    sj.get_jobs(company)
    assert company["ats_type"] == ""


@pytest.mark.network
def test_scrape_movingimage_detail_failures(monkeypatch):
    from tests.helpers.http_mock import MockResponse, load_ats_fixture

    listing = load_ats_fixture("movingimage.html")
    install_requests_mock(
        monkeypatch,
        get_routes={
            "movingimage.com/careers": text_response(listing),
            "movingimage.com/careers/backend-engineer": MockResponse(status_code=404, text=""),
        },
    )
    jobs = sj.scrape_movingimage("https://www.movingimage.com/careers", relevant_only=False)
    assert jobs


@pytest.mark.integration
def test_catalog_postgres_migrate_paths(pg_db, sample_country_data):
    from relocation_jobs.catalog_db import export_country_archive, load_country_for_path, migrate_from_json_files
    from relocation_jobs.paths import data_dir
    import json

    save_country("uk", sample_country_data, export_archive=False)
    path = export_country_archive("uk")
    assert path is not None
    key, data = load_country_for_path("uk_companies.json")
    assert key == "uk"

    json_path = data_dir() / "uk_companies.json"
    json_path.write_text(json.dumps(sample_country_data), encoding="utf-8")
    migrate_from_json_files()


@pytest.mark.integration
def test_db_postgres_connect_postgres(monkeypatch):
    import relocation_jobs.db as db_module

    class FakePsycopg:
        @staticmethod
        def connect(url, row_factory=None, **kwargs):
            return FakePgConnection()

    fake_module = type(sys)("psycopg")
    fake_module.connect = FakePsycopg.connect
    fake_rows = type(sys)("psycopg.rows")
    fake_rows.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_rows)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@localhost/db")
    conn = db_module._connect_postgres()
    assert conn is not None
