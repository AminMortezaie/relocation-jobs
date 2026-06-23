"""Cross-module integration and API edge-case coverage."""

from __future__ import annotations

import copy
import importlib
import json
import subprocess
import sys
import threading
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from tests.helpers.passwords import hash_test_password

from relocation_jobs.catalog_db import (
    init_catalog_schema,
    load_country_catalog,
    save_country_catalog,
    touch_country_meta,
    upsert_company,
)
from relocation_jobs.db import (
    clear_company_tracking,
    count_jobs_applied_db,
    count_jobs_applied_today_db,
    create_user,
    get_user_by_username,
    init_db,
    load_company_tracking,
    load_job_status_history,
    load_job_tracking,
    rename_company_tracking,
    set_company_applied_db,
    set_company_awaiting_response_db,
    set_job_applied_db,
    set_job_ats_score_db,
    set_job_looking_to_apply_db,
    set_job_not_for_me_db,
    set_job_rejected_db,
    set_job_seen_db,
    set_job_waiting_referral_db,
    sync_company_applied_from_jobs_db,
    tracking_is_empty,
)
from relocation_jobs.services.catalog_service import (
    _resolve_status_history,
    _tracking_bool,
    flatten_companies,
)
from relocation_jobs.services.company_service import (
    add_company,
    add_manual_jobs,
    remove_company,
    rename_company,
    update_company_careers,
    update_company_city,
)
from relocation_jobs.services.job_service import (
    _normalize_linkedin_url,
    set_job_not_for_me,
)
from tests.helpers.postgres_mock import FakePgConnection, install_postgres_mock


@pytest.fixture
def rich_catalog(seeded_catalog, sample_country_data):
    data = copy.deepcopy(sample_country_data)
    save_country_catalog("uk", data)
    return data

def test_reset_password_load_env_import_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "dotenv":
            raise ImportError("no dotenv")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from relocation_jobs.reset_password import _load_env

    _load_env()  # should not raise


def test_location_tags_short_country_token():
    from relocation_jobs.core.location_tags import (
        _unsupported_country_key_from_text,
        job_matches_expected_locations,
    )

    assert _unsupported_country_key_from_text(" office in u.s. only ") == "usa"
    expected = [{"country": "uk", "city": "London"}]
    ok, reason = job_matches_expected_locations({"location": "United States"}, expected)
    assert ok is False
    assert "unsupported country" in reason


def test_location_tags_format_location_list_and_numeric():
    from relocation_jobs.core.location_tags import _format_location_piece, job_listing_location_texts

    assert _format_location_piece(["Paris", {"city": "Lyon"}]) == "Paris | Lyon"
    assert _format_location_piece(42) == "42"
    texts = job_listing_location_texts({"locations": [999]})
    assert texts == ["999"]


def test_location_tags_city_only_match_and_remote_only():
    from relocation_jobs.core.location_tags import job_matches_expected_locations

    expected = [{"country": "uk", "city": "London"}]
    ok, _ = job_matches_expected_locations({"location": "London"}, expected)
    assert ok is True

    ok, reason = job_matches_expected_locations({"location": "Remote"}, expected)
    assert ok is False
    assert reason == "remote only"


def test_location_tags_unsupported_country_key():
    from relocation_jobs.core.location_tags import job_matches_expected_locations

    expected = [{"country": "uk", "city": "London"}]
    ok, reason = job_matches_expected_locations({"location": "Toronto, Canada"}, expected)
    assert ok is False
    assert "unsupported country" in reason


def test_location_tags_city_mismatch_explicit():
    from relocation_jobs.core.location_tags import job_matches_expected_locations

    expected = [{"country": "uk", "city": "London"}]
    ok, reason = job_matches_expected_locations({"location": "Birmingham, UK"}, expected)
    assert ok is False
    assert reason == "city mismatch"


def test_location_tags_location_mismatch_fallback():
    from relocation_jobs.core.location_tags import job_matches_expected_locations

    expected = [{"country": "uk", "city": "London"}]
    ok, reason = job_matches_expected_locations({"location": "xyz ambiguous place"}, expected)
    assert ok is True
    assert reason is None


def test_discover_careers_playwright_button_click(monkeypatch):
    from relocation_jobs.build_companies import discover_careers_playwright

    mock_btn = MagicMock()
    mock_btn.inner_text.return_value = "View all jobs"
    mock_btn.evaluate.return_value = "button"

    mock_link = MagicMock()
    mock_link.get_attribute.return_value = "https://boards.greenhouse.io/co/jobs"
    mock_link.inner_text.return_value = "Careers"

    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.query_selector_all.side_effect = [
        [mock_link],
        [mock_btn, mock_link],
    ]

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    monkeypatch.setattr(
        "relocation_jobs.build_companies.sync_playwright",
        lambda: MagicMock(__enter__=lambda s: mock_pw, __exit__=lambda *a: None),
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.probe_common_paths",
        lambda base: [],
    )

    result = discover_careers_playwright("https://example.com")
    assert result is not None
    mock_btn.click.assert_called_once()


def test_discover_careers_playwright_button_inner_text_error(monkeypatch):
    from relocation_jobs.build_companies import discover_careers_playwright

    bad_el = MagicMock()
    bad_el.inner_text.side_effect = RuntimeError("no text")

    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.query_selector_all.side_effect = [[], [bad_el]]

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    monkeypatch.setattr(
        "relocation_jobs.build_companies.sync_playwright",
        lambda: MagicMock(__enter__=lambda s: mock_pw, __exit__=lambda *a: None),
    )
    monkeypatch.setattr("relocation_jobs.build_companies.probe_common_paths", lambda b: [])

    assert discover_careers_playwright("https://example.com") is None


def test_discover_from_relocate_paths(monkeypatch):
    from relocation_jobs.build_companies import discover_from_relocate
    from tests.helpers.http_mock import MockResponse, install_requests_mock

    html = """
    <a class="website-link" href="https://jobs.example.com/careers">Official website</a>
    """
    install_requests_mock(
        monkeypatch,
        get_routes={"relocate.me": MockResponse(text=html, status_code=200)},
        module="relocation_jobs.build_companies",
    )
    assert discover_from_relocate("Job Site Co") == "https://jobs.example.com/careers"


def test_discover_careers_static_non_http_href(monkeypatch):
    from relocation_jobs.build_companies import discover_careers_static
    from tests.helpers.http_mock import MockResponse, install_requests_mock

    page = '<a href="mailto:jobs@example.com">Jobs</a>'
    install_requests_mock(
        monkeypatch,
        get_routes={"example.com": MockResponse(text=page, status_code=200)},
        module="relocation_jobs.build_companies",
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.probe_common_paths",
        lambda b: [],
    )
    assert discover_careers_static("example.com") is None


def test_discover_careers_url_playwright_fallback(monkeypatch):
    from relocation_jobs.build_companies import discover_careers_url

    monkeypatch.setattr("relocation_jobs.build_companies.discover_from_relocate", lambda n: None)
    monkeypatch.setattr(
        "relocation_jobs.build_companies.discover_careers_static",
        lambda u: None,
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.discover_careers_playwright",
        lambda u: "https://example.com/careers",
    )
    url = discover_careers_url({"name": "Co", "careers_url": "https://example.com"})
    assert url == "https://example.com/careers"


def test_build_companies_main_module_entry(monkeypatch, db, sample_country_data):
    from relocation_jobs import build_companies

    monkeypatch.setattr(
        build_companies,
        "load_country",
        lambda c: (sample_country_data, "uk"),
    )
    monkeypatch.setattr(build_companies, "save_country", lambda k, d: None)
    monkeypatch.setattr(build_companies.sys, "argv", ["build_companies.py", "uk", "--sort-only"])
    build_companies.main()


def test_build_companies_resolve_country_alias(monkeypatch, db, sample_country_data):
    from relocation_jobs.build_companies import load_country

    save_country_catalog("uk", sample_country_data)
    data, key = load_country("england")
    assert key == "uk"
    assert data["companies"]


def test_postgres_init_and_tracking(pg_db, sample_country_data):
    user = create_user("pguser", hash_test_password("pass123456"))
    uid = user["id"]
    save_country_catalog("uk", sample_country_data)

    set_job_applied_db(uid, "uk", "Acme Backend Ltd", "https://example.com/j/1", True, job_title="Dev")
    set_job_rejected_db(uid, "uk", "Acme Backend Ltd", "https://example.com/j/2", True)
    set_job_seen_db(uid, "uk", "Acme Backend Ltd", "https://example.com/j/1", True)
    set_job_looking_to_apply_db(uid, "uk", "Acme Backend Ltd", "https://example.com/j/1", True)
    set_job_ats_score_db(uid, "uk", "Acme Backend Ltd", "https://example.com/j/1", 90)
    set_job_not_for_me_db(uid, "uk", "Acme Backend Ltd", "https://example.com/j/2", not_for_me=True, reason="pay")
    set_job_waiting_referral_db(
        uid, "uk", "Acme Backend Ltd", "https://example.com/j/1", True,
        linkedin_url="https://linkedin.com/in/test",
    )
    set_company_applied_db(uid, "uk", "Acme Backend Ltd", True)
    set_company_awaiting_response_db(uid, "uk", "Acme Backend Ltd", True)
    sync_company_applied_from_jobs_db(uid, "uk", "Acme Backend Ltd")
    rename_company_tracking("uk", "Acme Backend Ltd", "Acme Renamed")

    assert not tracking_is_empty()
    assert load_job_tracking(uid)
    assert load_company_tracking(uid)
    assert load_job_status_history(uid)
    assert count_jobs_applied_db(uid) >= 1
    assert count_jobs_applied_today_db(uid, timezone_name="UTC") >= 0

    clear_company_tracking("uk", "Acme Renamed")
    assert tracking_is_empty()


def test_postgres_catalog_upsert(pg_db, sample_country_data):
    save_country_catalog("uk", sample_country_data)
    upsert_company(
        "uk",
        {
            "name": "Pg Co",
            "city": "London",
            "locations": [{"country": "uk", "city": "London"}],
            "matching_jobs": [
                {"title": "Dev", "url": "https://example.com/pg/1?gh_jid=1", "fetched": "2025-06-01"},
            ],
        },
    )
    touch_country_meta("uk", last_fetch_new_jobs=3, total=5)
    data = load_country_catalog("uk")
    assert any(c["name"] == "Pg Co" for c in data["companies"])


def test_postgres_reconnect_when_closed(tmp_data_dir, monkeypatch):
    import relocation_jobs.db as db_module

    fake = install_postgres_mock(monkeypatch)
    init_db()
    conn1 = db_module.get_connection()
    conn1.close()
    conn2 = db_module.get_connection()
    assert conn2 is not None
    assert not conn2.closed


def test_db_read_retries_operational_error(tmp_data_dir, monkeypatch):
    from psycopg import OperationalError

    import relocation_jobs.core.db as core

    install_postgres_mock(monkeypatch)
    init_db()
    create_user("retryuser", hash_test_password("password123"))

    conn = core._acquire_connection()
    real_execute = conn.execute
    calls = {"n": 0}

    def flaky_execute(sql, params=()):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("SSL connection has been closed unexpectedly")
        return real_execute(sql, params)

    conn.execute = flaky_execute
    monkeypatch.setattr(core, "_acquire_connection", lambda: conn)
    monkeypatch.setattr(core, "_reset_pg_connection", lambda: None)

    user = get_user_by_username("retryuser")
    assert user is not None
    assert user["username"] == "retryuser"
    assert calls["n"] == 2


def test_get_connection_serializes_concurrent_reads(tmp_data_dir, monkeypatch):
    install_postgres_mock(monkeypatch)
    init_db()
    create_user("threaduser", hash_test_password("password123"))

    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(20):
                user = get_user_by_username("threaduser")
                assert user is not None
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors


def test_schema_migrations_run_once(tmp_data_dir, monkeypatch):
    import relocation_jobs.core.migrations as migrations

    install_postgres_mock(monkeypatch)
    calls = {"n": 0}
    real_backfill = migrations._backfill_job_status_events

    def counted_backfill(conn):
        calls["n"] += 1
        return real_backfill(conn)

    monkeypatch.setattr(migrations, "_backfill_job_status_events", counted_backfill)

    from relocation_jobs.core.db import reset_db_initialized

    reset_db_initialized()
    init_db(force=True)
    init_db(force=True)
    assert calls["n"] == 1


def test_load_country_cache_reuses_db_read(tmp_data_dir, monkeypatch, sample_country_data):
    from relocation_jobs.catalog_db import invalidate_country_cache, load_country_catalog, save_country_catalog

    install_postgres_mock(monkeypatch)
    init_db()
    save_country_catalog("uk", sample_country_data)

    reads = {"n": 0}
    real_load = __import__(
        "relocation_jobs.catalog.reads",
        fromlist=["load_country_from_db"],
    ).load_country_from_db

    def counted_load(country_key: str):
        reads["n"] += 1
        return real_load(country_key)

    monkeypatch.setattr(
        "relocation_jobs.catalog.reads.load_country_from_db",
        counted_load,
    )

    invalidate_country_cache()
    assert load_country_catalog("uk") is not None
    assert load_country_catalog("uk") is not None
    assert reads["n"] == 1

    save_country_catalog("uk", sample_country_data)
    load_country_catalog("uk")
    assert reads["n"] == 2


def test_panel_data_linkedin_url_normalization():
    from relocation_jobs.services.job_service import _normalize_linkedin_url

    assert _normalize_linkedin_url("linkedin.com/in/foo").startswith("https://")
    assert _normalize_linkedin_url("") == ""
    with pytest.raises(ValueError, match="LinkedIn"):
        _normalize_linkedin_url("https://example.com/in/foo")


def test_panel_data_resolve_status_history_alias(db, seeded_catalog, test_user):
    from relocation_jobs.db import set_job_applied_db
    from relocation_jobs.services.catalog_service import _resolve_status_history, flatten_companies
    from relocation_jobs.services.job_service import set_job_applied

    uid = test_user["id"]
    company = seeded_catalog["companies"][0]["name"]
    url = seeded_catalog["companies"][0]["matching_jobs"][0]["url"]
    alias = url.replace("https://", "https://www.")
    set_job_applied_db(uid, "uk", company, alias, True, job_title="Dev")

    history = load_job_status_history(uid)
    merged = _resolve_status_history(
        history,
        country="uk",
        company_name=company,
        job={"url": url, "idempotency_key": "x"},
    )
    assert merged["applied"] or merged["applied_events"]

    companies, _, _ = flatten_companies(
        "uk",
        user_id=uid,
        hide_position_applied=True,
        hide_position_rejected=True,
        position_applied_only=True,
        position_rejected_only=True,
        position_looking_to_apply_only=True,
        visa_only=True,
        fetch_ok_only=True,
        fetch_problem_only=True,
        location="uk:London",
        city="London",
    )
    assert isinstance(companies, list)


def test_panel_data_enrich_and_detect(db, monkeypatch):
    from relocation_jobs.services.catalog_service import list_ats_types
    from relocation_jobs.services.company_service import (
        add_manual_jobs,
        detect_ats_for_company,
        enrich_new_company,
        rename_company,
        set_company_fetch_problem,
        update_company_city,
    )

    monkeypatch.setattr(
        "relocation_jobs.services.company_service.fetch_relocate_metadata",
        lambda name, country_key=None: {"city": "London", "size": "51-200", "country": "uk"},
    )
    monkeypatch.setattr(
        "relocation_jobs.services.company_service.detect_ats_for_company",
        lambda *a, **k: ("greenhouse", "https://boards.greenhouse.io/newco"),
    )
    company = enrich_new_company("New Co", "https://boards.greenhouse.io/newco", "uk", ats_hint="greenhouse")
    assert company["name"] == "New Co"
    assert list_ats_types()

    save_country_catalog("uk", {"source": "t", "companies": [company], "total": 1})
    update_company_city("uk", "New Co", locations=[{"country": "uk", "city": "Manchester"}])
    add_manual_jobs("uk", "New Co", [{"title": "Role", "url": "https://example.com/manual/1"}])
    set_company_fetch_problem("uk", "New Co", True)
    rename_company("uk", "New Co", "Renamed Co")

    monkeypatch.setattr(
        "relocation_jobs.services.company_service.detect_ats_for_hint",
        lambda *a: ("lever", "https://jobs.lever.co/x"),
    )
    ats_type, ats_url = detect_ats_for_company("Co", "https://example.com", ats_hint="lever")
    assert ats_type == "lever"


def test_panel_data_fetch_relocate_metadata(monkeypatch):
    from relocation_jobs.services.company_service import fetch_relocate_metadata

    html = """
    <div class="company-location">London, UK</div>
    <div class="company-facts__heading">Company size</div>
    <div>51 - 200 employees</div>
    """
    monkeypatch.setattr(
        "relocation_jobs.services.company_service.requests.get",
        lambda *a, **k: type("R", (), {"status_code": 200, "text": html})(),
    )
    meta = fetch_relocate_metadata("Acme", country_key="uk")
    assert meta.get("city") or meta.get("size")


def test_panel_data_helpers(seeded_catalog):
    from relocation_jobs.services.catalog_service import (
        _ats_score_value,
        _title_from_tracked_url,
        _company_activity_ts,
        _tracking_bool,
        _load_country_data,
    )

    assert _ats_score_value("85") == 85
    assert _ats_score_value("999") is None
    assert _title_from_tracked_url("https://boards.greenhouse.io/x/jobs/1?gh_jid=42") == "Role 42"
    assert _title_from_tracked_url("https://example.com/jobs/backend-engineer") == "backend engineer"
    assert _tracking_bool("false") is False
    assert _tracking_bool(1) is True

    company = seeded_catalog["companies"][0]
    assert _company_activity_ts(company, company.get("matching_jobs") or [])
    assert _load_country_data("uk")["companies"]


JOB_ENDPOINTS = [
    "/api/jobs/applied",
    "/api/jobs/rejected",
    "/api/jobs/reapply",
    "/api/jobs/ats-score",
    "/api/jobs/waiting-referral",
    "/api/jobs/not-for-me",
    "/api/jobs/looking-to-apply",
    "/api/jobs/seen",
]

COMPANY_ENDPOINTS = [
    "/api/companies/applied",
    "/api/companies/awaiting-response",
    "/api/companies/remove",
    "/api/companies/name",
    "/api/companies/careers",
    "/api/companies/city",
    "/api/companies/fetch-problem",
    "/api/companies/fetch-ok",
    "/api/companies/jobs/manual-add",
]


@pytest.mark.integration
@pytest.mark.parametrize("path", JOB_ENDPOINTS)
def test_panel_api_job_validation_400(auth_client, path):
    for payload, code in [
        ({"country": "all", "company": "X", "url": "https://x.com"}, 400),
        ({"country": "nope", "company": "X", "url": "https://x.com"}, 400),
        ({"country": "uk", "company": "", "url": ""}, 400),
    ]:
        assert auth_client.post(path, json=payload).status_code == code


@pytest.mark.integration
@pytest.mark.parametrize("path", COMPANY_ENDPOINTS)
def test_panel_api_company_validation_400(auth_client, path):
    for payload, code in [
        ({"country": "all", "company": "X"}, 400),
        ({"country": "nope", "company": "X"}, 400),
        ({"country": "uk", "company": ""}, 400),
    ]:
        assert auth_client.post(path, json=payload).status_code == code


def test_panel_api_value_error_paths(auth_client, rich_catalog, monkeypatch):
    import relocation_jobs.panel_server as ps

    ctx = {
        "country": "uk",
        "company": rich_catalog["companies"][0]["name"],
        "url": rich_catalog["companies"][0]["matching_jobs"][0]["url"],
    }

    def boom(*a, **k):
        raise ValueError("bad input")

    for route, target in [
        ("/api/jobs/applied", "relocation_jobs.web.deps.set_job_applied"),
        ("/api/jobs/rejected", "relocation_jobs.web.deps.set_job_rejected"),
        ("/api/jobs/reapply", "relocation_jobs.web.deps.set_job_reapply"),
        ("/api/jobs/ats-score", "relocation_jobs.web.deps.set_job_ats_score"),
        ("/api/jobs/waiting-referral", "relocation_jobs.web.deps.set_job_waiting_referral"),
        ("/api/jobs/not-for-me", "relocation_jobs.web.deps.set_job_not_for_me"),
        ("/api/jobs/looking-to-apply", "relocation_jobs.web.deps.set_job_looking_to_apply"),
        ("/api/jobs/seen", "relocation_jobs.web.deps.set_job_seen"),
        ("/api/companies/applied", "relocation_jobs.web.deps.set_company_applied"),
        ("/api/companies/awaiting-response", "relocation_jobs.web.deps.set_company_awaiting_response"),
    ]:
        monkeypatch.setattr(target, boom)
        resp = auth_client.post(route, json={**ctx, "applied": True, "ats_score": 50})
        assert resp.status_code == 400


def test_panel_api_ats_score_bounds(auth_client, rich_catalog):
    ctx = {
        "country": "uk",
        "company": rich_catalog["companies"][0]["name"],
        "url": rich_catalog["companies"][0]["matching_jobs"][0]["url"],
    }
    assert auth_client.post("/api/jobs/ats-score", json={**ctx, "ats_score": 101}).status_code == 400
    assert auth_client.post("/api/jobs/ats-score", json={**ctx, "ats_score": -1}).status_code == 400


def test_panel_server_main(monkeypatch):
    import relocation_jobs.panel_server as ps

    monkeypatch.setattr(ps.app, "run", lambda **kw: None)
    monkeypatch.delenv("PORT", raising=False)
    ps.main()
    monkeypatch.setenv("PORT", "8080")
    ps.main()


def test_panel_server_module_entry(monkeypatch):
    import relocation_jobs.panel_server as ps

    monkeypatch.setattr(ps, "main", lambda: None)
    with pytest.raises(SystemExit):
        import runpy
        runpy.run_module("relocation_jobs.panel_server", run_name="__main__")


def test_panel_server_scrape_helpers(monkeypatch, db, seeded_catalog):
    import relocation_jobs.panel_server as ps

    ps._reset_fetch_run_state(country="uk", company=None, file_name="uk_companies.json", concurrency=1, user_id=1)
    assert ps._activity_from_scrape_line("Greenhouse error: timeout")["message"]
    assert ps._activity_from_scrape_line("Lever API") is None
    assert ps._log("") is None

    ps._log("Starting (3 to process)")
    assert ps._fetch_state["progress"]["total"] == 3

    class FakeProc:
        stdout = iter(["plain log line", "@@PROGRESS@@not-json"])
        returncode = 2

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 2

        def terminate(self):
            pass

        def kill(self):
            pass

    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)
    monkeypatch.setattr(ps.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(ps, "touch_country_meta", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fail")))

    with ps._fetch_lock:
        ps._fetch_state.update({"running": True, "country": "uk", "new_jobs_total": 0})
    ps._run_scrape("uk", skip_filled=False, concurrency=128, company="Acme Backend Ltd")
    assert ps._fetch_state["exit_code"] == 2


def test_panel_server_scrape_exception(monkeypatch):
    import relocation_jobs.panel_server as ps

    ps._reset_fetch_run_state(country="uk", company=None, file_name="uk_companies.json", concurrency=1, user_id=1)
    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)
    monkeypatch.setattr(ps.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with ps._fetch_lock:
        ps._fetch_state["running"] = True
    ps._run_scrape("uk", skip_filled=False, concurrency=1)
    assert ps._fetch_state["exit_code"] == 1


def test_panel_fetch_endpoints(auth_client, rich_catalog, monkeypatch):
    import relocation_jobs.panel_server as ps

    assert auth_client.post("/api/fetch/cancel").status_code == 400

    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", False)
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    assert auth_client.post("/api/fetch", json={"country": "uk"}).status_code == 503

    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "0")
    assert auth_client.post("/api/fetch", json={"country": "uk"}).status_code == 503

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    assert auth_client.post("/api/fetch", json={"country": "all"}).status_code == 400
    assert auth_client.post("/api/fetch", json={"country": "nope"}).status_code == 400

    assert auth_client.post("/api/companies/fetch", json={"country": "all", "company": "X"}).status_code == 400
    assert auth_client.post("/api/companies/fetch", json={"country": "uk", "company": ""}).status_code == 400


def test_panel_companies_add_conflict(auth_client, rich_catalog, monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.web.deps.add_company",
        lambda *a, **k: (_ for _ in ()).throw(LookupError("exists")),
    )
    resp = auth_client.post(
        "/api/companies",
        json={"name": "Dup Co", "careers_url": "https://boards.greenhouse.io/dup", "country": "uk"},
    )
    assert resp.status_code == 409


def test_panel_companies_rename_conflict(auth_client, rich_catalog):
    company = rich_catalog["companies"][0]["name"]
    resp = auth_client.post(
        "/api/companies/name",
        json={"country": "uk", "company": company, "new_name": "Totally New Name Ltd"},
    )
    assert resp.status_code == 200


def test_normalize_linkedin_url_variants():
    assert _normalize_linkedin_url("linkedin.com/in/user") == "https://linkedin.com/in/user"
    with pytest.raises(ValueError):
        _normalize_linkedin_url("https://twitter.com/user")


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


def test_flatten_without_user_not_for_me_in_json(seeded_catalog, sample_country_data):
    data = copy.deepcopy(sample_country_data)
    data["companies"][0]["matching_jobs"][0]["not_for_me"] = True
    save_country_catalog("uk", data)
    companies, _, _ = flatten_companies("uk", hide_applied=True, hide_empty=True, not_applied_only=True)
    assert isinstance(companies, list)


def test_flatten_all_countries_and_location_filter(seeded_catalog, test_user):
    companies, meta, _ = flatten_companies(None, user_id=test_user["id"], location="uk:London")
    assert meta
    assert isinstance(companies, list)


def test_company_crud_edge_cases(db, sample_country_data, monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.services.company_service.fetch_relocate_metadata",
        lambda *a, **k: {"city": "London", "size": "51-200", "country": "uk"},
    )
    monkeypatch.setattr(
        "relocation_jobs.services.company_service.detect_ats_for_company",
        lambda *a, **k: ("greenhouse", "https://boards.greenhouse.io/x"),
    )
    add_company("Edge Co", "https://boards.greenhouse.io/x", "uk")
    update_company_careers("uk", "Edge Co", "https://boards.greenhouse.io/x2", redetect_ats=False)
    rename_company("uk", "Edge Co", "Edge Renamed")
    remove_company("uk", "Edge Renamed")


def test_set_job_not_for_me_panel(db, seeded_catalog, test_user):
    company = seeded_catalog["companies"][0]["name"]
    url = seeded_catalog["companies"][0]["matching_jobs"][0]["url"]
    result = set_job_not_for_me("uk", company, url, user_id=test_user["id"], not_for_me=True, reason="pay")
    assert result["not_for_me"] is True


def test_panel_data_fetch_relocate_errors(monkeypatch):
    import requests
    from relocation_jobs.services.company_service import fetch_relocate_metadata

    def boom(*a, **k):
        raise requests.RequestException("network")

    monkeypatch.setattr("relocation_jobs.services.company_service.requests.get", boom)
    assert fetch_relocate_metadata("Missing Co", country_key="uk") == {}


def test_panel_data_validation_errors(db):
    from relocation_jobs.services.company_service import (
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


def test_db_postgres_connect_postgres(monkeypatch):
    import relocation_jobs.core.db as core

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
    conn = core._connect_postgres()
    assert conn is not None

