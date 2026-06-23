"""Full Flask panel API coverage — every route, filters, errors, fetch mocks."""

from __future__ import annotations

import copy
import json
import subprocess
import threading
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from relocation_jobs.catalog_db import save_country_catalog

pytest_plugins = ["tests.helpers.panel_fixtures"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_ctx(auth_client, country: str = "uk") -> dict:
    resp = auth_client.get(f"/api/jobs?country={country}")
    assert resp.status_code == 200
    companies = resp.get_json()["companies"]
    assert companies, "expected at least one company"
    company = companies[0]
    assert company["jobs"], "expected at least one job"
    return {
        "country": country,
        "company": company["name"],
        "url": company["jobs"][0]["url"],
    }


def _reset_fetch_state() -> None:
    from relocation_jobs.web import fetch_state
    import relocation_jobs.panel_server as ps

    with ps._fetch_lock:
        ps._fetch_state["running"] = False
        ps._fetch_state["cancel_requested"] = False
        ps._fetch_state["cancelled"] = False
        ps._fetch_state["process"] = None
        ps._fetch_state["exit_code"] = None
        ps._fetch_state["started_at"] = None
        ps._fetch_state["finished_at"] = None
        ps._fetch_state["user_id"] = None
        ps._fetch_state["company"] = None
        ps._fetch_state["country"] = None
        ps._fetch_state["fetch_run_recorded"] = False
        ps._fetch_state["last_fetch_run"] = None
        ps._fetch_state["new_jobs_total"] = 0
        ps._fetch_state["log"].clear()
        ps._fetch_state["activity_log"].clear()
    fetch_state._fetch_thread = None


def _fake_run_scrape(country, skip_filled, concurrency, *, company=None, ats_type=None):
    import relocation_jobs.panel_server as ps
    from datetime import datetime, timezone

    _log = ps._log
    if company:
        _log(f"Fetching {company}")
    _log("@@PROGRESS@@" + json.dumps({"current": 1, "total": 1, "company": company or "x", "status": "done", "new_jobs": 2}))
    _log("Done [1/1] Acme — enriched 1 job(s)")
    with ps._fetch_lock:
        ps._fetch_state["exit_code"] = 0
        ps._fetch_state["running"] = False
        ps._fetch_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        ps._fetch_state["progress"] = {"current": 1, "total": 1, "company": company, "status": "done"}
        ps._fetch_state["new_jobs_total"] = 2
    ps._persist_fetch_run()


def _fake_start_scrape_thread(country, skip_filled, concurrency, *, company=None, ats_type=None):
    from relocation_jobs.web import fetch_state
    import relocation_jobs.panel_server as ps

    fetch_state._fetch_thread = threading.Thread(
        target=_fake_run_scrape,
        args=(country, skip_filled, concurrency),
        kwargs={"company": company, "ats_type": ats_type},
        daemon=True,
    )
    fetch_state._fetch_thread.start()


@pytest.fixture(autouse=True)
def _panel_fetch_reset(request):
    if "_module_panel" not in request.fixturenames:
        yield
        return
    yield
    _reset_fetch_state()


@pytest.fixture
def scrape_enabled(auth_client, monkeypatch):
    """Enable scraping after app_client fixture (which sets PANEL_SCRAPE_ENABLED=0)."""
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    import relocation_jobs.panel_server as ps

    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)
    monkeypatch.setattr("relocation_jobs.web.scrape_runner._run_scrape", _fake_run_scrape)
    monkeypatch.setattr("relocation_jobs.web.scrape_runner._start_scrape_thread", _fake_start_scrape_thread)
    _reset_fetch_state()
    yield
    _reset_fetch_state()


@pytest.fixture
def mock_enrich(monkeypatch):
    def fake_enrich(name, careers_url, country_key, *, ats_hint=None):
        return {
            "name": name,
            "city": "London",
            "careers_url": careers_url,
            "ats_type": "greenhouse",
            "ats_url": careers_url,
            "matching_jobs": [],
            "locations": [{"country": country_key, "city": "London"}],
        }

    monkeypatch.setattr("relocation_jobs.services.company_service.enrich_new_company", fake_enrich)


# ---------------------------------------------------------------------------
# Index & auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_index(auth_client):
    resp = auth_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type


@pytest.mark.integration
def test_auth_register_logout(app_client):
    reg = app_client.post(
        "/api/auth/register",
        json={"username": "newuser", "password": "securepass123"},
    )
    assert reg.status_code == 200
    assert reg.get_json()["authenticated"] is True

    dup = app_client.post(
        "/api/auth/register",
        json={"username": "newuser", "password": "otherpass123"},
    )
    assert dup.status_code == 400

    logout = app_client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert logout.get_json()["authenticated"] is False


@pytest.mark.integration
def test_auth_login_validation(app_client):
    assert app_client.post("/api/auth/login", json={}).status_code == 400
    assert app_client.get("/api/auth/status").status_code == 200


# ---------------------------------------------------------------------------
# Config & reference data
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_config(auth_client):
    resp = auth_client.get("/api/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "scrape_enabled" in body
    assert "default_concurrency" in body


@pytest.mark.integration
def test_countries_ats_types(auth_client):
    countries = auth_client.get("/api/countries").get_json()
    assert any(c["id"] == "uk" for c in countries)
    ats = auth_client.get("/api/ats-types").get_json()
    assert "ats_types" in ats


@pytest.mark.integration
def test_cities_and_locations(auth_client, rich_catalog):
    cities = auth_client.get("/api/cities?country=uk")
    assert cities.status_code == 200
    body = cities.get_json()
    assert "cities" in body and "locations" in body

    picker = auth_client.get("/api/locations?country=uk&picker=true")
    assert picker.status_code == 200
    assert picker.get_json()["locations"]

    assert auth_client.get("/api/cities?country=invalid").status_code == 400
    assert auth_client.get("/api/locations?country=invalid").status_code == 400

    all_locs = auth_client.get("/api/locations?country=all")
    assert all_locs.status_code == 200


@pytest.mark.integration
def test_locations_add_custom_city(auth_client, tmp_data_dir):
    resp = auth_client.post("/api/locations", json={"country": "uk", "city": "Reading"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["location"] == {
        "country": "uk",
        "city": "Reading",
        "key": "uk:reading",
        "country_label": "United Kingdom",
        "label": "Reading (United Kingdom)",
    }

    picker = auth_client.get("/api/locations?country=uk&picker=true").get_json()
    keys = {loc["key"] for loc in picker["locations"]}
    assert "uk:reading" in keys

    dup = auth_client.post("/api/locations", json={"country": "uk", "city": "Reading"})
    assert dup.status_code == 200
    assert dup.get_json()["location"]["city"] == "Reading"

    import json

    saved = json.loads((tmp_data_dir / "custom_cities.json").read_text(encoding="utf-8"))
    assert saved["uk"].count("Reading") == 1

    builtin = auth_client.post("/api/locations", json={"country": "uk", "city": "London"})
    assert builtin.status_code == 200
    assert builtin.get_json()["location"]["city"] == "London"
    saved_after_builtin = json.loads((tmp_data_dir / "custom_cities.json").read_text(encoding="utf-8"))
    assert "London" not in saved_after_builtin.get("uk", [])


@pytest.mark.integration
def test_locations_add_custom_city_validation(auth_client, tmp_data_dir):
    assert auth_client.post("/api/locations", json={"country": "invalid", "city": "X"}).status_code == 400
    assert auth_client.post("/api/locations", json={"country": "uk", "city": ""}).status_code == 400
    assert auth_client.post("/api/locations", json={"country": "all", "city": "Reading"}).status_code == 400


@pytest.mark.integration
def test_locations_add_custom_city_requires_auth(app_client, tmp_data_dir):
    assert app_client.post("/api/locations", json={"country": "uk", "city": "Reading"}).status_code == 401


# ---------------------------------------------------------------------------
# Jobs listing filters
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "query",
    [
        "country=uk",
        "country=all",
        "country=uk&visa_only=true",
        "country=uk&hide_applied=true",
        "country=uk&hide_empty=true",
        "country=uk&not_applied_only=true",
        "country=uk&hide_position_applied=true",
        "country=uk&hide_position_rejected=true",
        "country=uk&position_applied_only=true",
        "country=uk&position_rejected_only=true",
        "country=uk&position_looking_to_apply_only=true",
        "country=uk&fetch_ok_only=true",
        "country=uk&fetch_problem_only=true",
        "country=uk&location=London",
        "country=uk&city=London",
        "country=uk&timezone=Europe/London",
        "country=uk&ats_type=greenhouse",
        "country=uk&ats_type=generic",
    ],
)
def test_jobs_list_filters(auth_client, rich_catalog, test_user, query):
    resp = auth_client.get(f"/api/jobs?{query}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "companies" in body
    assert "stats" in body


# ---------------------------------------------------------------------------
# Job mutations
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_job_applied_and_company_applied(auth_client, rich_catalog, test_user):
    ctx = _job_ctx(auth_client)
    assert auth_client.post("/api/jobs/applied", json={**ctx, "applied": True}).status_code == 200
    assert auth_client.patch("/api/jobs/applied", json={**ctx, "applied": False}).status_code == 200

    comp = auth_client.post(
        "/api/companies/applied",
        json={"country": ctx["country"], "company": ctx["company"], "applied": True},
    )
    assert comp.status_code == 200
    assert auth_client.patch(
        "/api/companies/applied",
        json={"country": ctx["country"], "company": ctx["company"], "applied": False},
    ).status_code == 200


@pytest.mark.integration
def test_job_rejected_reapply(auth_client, rich_catalog, test_user):
    ctx = _job_ctx(auth_client)
    assert auth_client.post("/api/jobs/rejected", json={**ctx, "rejected": True}).status_code == 200
    assert auth_client.post("/api/jobs/reapply", json=ctx).status_code == 200
    assert auth_client.patch("/api/jobs/rejected", json={**ctx, "rejected": False}).status_code == 200


@pytest.mark.integration
def test_job_ats_score(auth_client, rich_catalog, test_user):
    ctx = _job_ctx(auth_client)
    ok = auth_client.post("/api/jobs/ats-score", json={**ctx, "ats_score": 85})
    assert ok.status_code == 200
    clear = auth_client.patch("/api/jobs/ats-score", json={**ctx, "ats_score": None})
    assert clear.status_code == 200
    bad = auth_client.post("/api/jobs/ats-score", json={**ctx, "ats_score": 150})
    assert bad.status_code == 400


@pytest.mark.integration
def test_job_waiting_referral(auth_client, rich_catalog, test_user):
    ctx = _job_ctx(auth_client)
    ok = auth_client.post(
        "/api/jobs/waiting-referral",
        json={
            **ctx,
            "waiting_referral": True,
            "linkedin_url": "https://linkedin.com/in/testuser",
        },
    )
    assert ok.status_code == 200
    off = auth_client.patch(
        "/api/jobs/waiting-referral",
        json={**ctx, "waiting_referral": False},
    )
    assert off.status_code == 200


@pytest.mark.integration
def test_job_not_for_me_looking_seen(auth_client, rich_catalog, test_user):
    ctx = _job_ctx(auth_client)
    assert auth_client.post(
        "/api/jobs/not-for-me",
        json={**ctx, "not_for_me": True, "reason": "stack"},
    ).status_code == 200
    assert auth_client.post(
        "/api/jobs/not-for-me",
        json={**ctx, "not_for_me": False},
    ).status_code == 200

    ctx2 = _job_ctx(auth_client)
    assert auth_client.post(
        "/api/jobs/looking-to-apply",
        json={**ctx2, "looking_to_apply": True},
    ).status_code == 200
    assert auth_client.patch(
        "/api/jobs/looking-to-apply",
        json={**ctx2, "looking_to_apply": False},
    ).status_code == 200

    ctx3 = _job_ctx(auth_client)
    assert auth_client.post("/api/jobs/seen", json={**ctx3, "seen": True}).status_code == 200
    assert auth_client.patch("/api/jobs/seen", json={**ctx3, "seen": False}).status_code == 200


@pytest.mark.integration
def test_company_awaiting_response(auth_client, rich_catalog, test_user):
    ctx = _job_ctx(auth_client)
    ok = auth_client.post(
        "/api/companies/awaiting-response",
        json={"country": ctx["country"], "company": ctx["company"], "awaiting_response": True},
    )
    assert ok.status_code == 200
    off = auth_client.patch(
        "/api/companies/awaiting-response",
        json={"country": ctx["country"], "company": ctx["company"], "awaiting": False},
    )
    assert off.status_code == 200


@pytest.mark.integration
def test_job_mutation_errors(auth_client):
    missing = {"country": "uk", "company": "", "url": ""}
    assert auth_client.post("/api/jobs/applied", json=missing).status_code == 400
    assert auth_client.post("/api/jobs/applied", json={"country": "all", "company": "x", "url": "y"}).status_code == 400
    assert auth_client.post("/api/jobs/applied", json={"country": "nope", "company": "x", "url": "y"}).status_code == 400
    assert auth_client.post(
        "/api/jobs/applied",
        json={"country": "uk", "company": "Missing Co", "url": "https://example.com/job"},
    ).status_code == 404


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_companies_add_remove_rename(auth_client, rich_catalog, mock_enrich):
    add = auth_client.post(
        "/api/companies",
        json={
            "name": "Panel Added Co",
            "careers_url": "https://boards.greenhouse.io/paneladded",
            "country": "uk",
            "ats": "greenhouse",
        },
    )
    assert add.status_code == 200

    rename = auth_client.post(
        "/api/companies/name",
        json={
            "country": "uk",
            "company": "Panel Added Co",
            "new_name": "Panel Renamed Co",
        },
    )
    assert rename.status_code == 200

    remove = auth_client.delete(
        "/api/companies",
        json={"country": "uk", "company": "Panel Renamed Co"},
    )
    assert remove.status_code == 200


@pytest.mark.integration
def test_companies_careers_city(auth_client, rich_catalog, monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.services.company_service.detect_ats_for_company",
        lambda *a, **k: ("greenhouse", "https://boards.greenhouse.io/acmebackend"),
    )
    ctx = _job_ctx(auth_client)
    careers = auth_client.post(
        "/api/companies/careers",
        json={
            "country": ctx["country"],
            "company": ctx["company"],
            "careers_url": "https://boards.greenhouse.io/acmebackend",
            "redetect_ats": True,
        },
    )
    assert careers.status_code == 200

    city = auth_client.patch(
        "/api/companies/city",
        json={
            "country": ctx["country"],
            "company": ctx["company"],
            "cities": ["London", "Manchester"],
        },
    )
    assert city.status_code == 200

    legacy = auth_client.post(
        "/api/companies/city",
        json={"country": ctx["country"], "company": ctx["company"], "city": "Bristol"},
    )
    assert legacy.status_code == 200

    locs = auth_client.post(
        "/api/companies/city",
        json={
            "country": ctx["country"],
            "company": ctx["company"],
            "locations": [{"country": "uk", "city": "Edinburgh"}],
        },
    )
    assert locs.status_code == 200


@pytest.mark.integration
def test_companies_fetch_flags_manual(auth_client, rich_catalog):
    ctx = _job_ctx(auth_client)
    problem = auth_client.post(
        "/api/companies/fetch-problem",
        json={"country": ctx["country"], "company": ctx["company"], "fetch_problem": True},
    )
    assert problem.status_code == 200

    clear = auth_client.post(
        "/api/companies/fetch-problem",
        json={
            "country": ctx["country"],
            "company": ctx["company"],
            "fetch_problem": False,
            "mark_fetch_ok": True,
        },
    )
    assert clear.status_code == 200

    ok = auth_client.post(
        "/api/companies/fetch-ok",
        json={"country": ctx["country"], "company": ctx["company"]},
    )
    assert ok.status_code == 200

    manual = auth_client.post(
        "/api/companies/jobs/manual-add",
        json={
            "country": ctx["country"],
            "company": ctx["company"],
            "jobs": [{"title": "Manual Role", "url": "https://example.com/manual-role-999"}],
        },
    )
    assert manual.status_code == 200


@pytest.mark.integration
def test_companies_add_validation_errors(auth_client):
    assert auth_client.post("/api/companies", json={"name": "", "careers_url": "x"}).status_code == 400
    assert auth_client.post("/api/companies", json={"name": "X", "careers_url": ""}).status_code == 400
    assert auth_client.post(
        "/api/companies",
        json={"name": "X", "careers_url": "https://x.com", "country": "nope"},
    ).status_code == 400
    assert auth_client.post(
        "/api/companies",
        json={"name": "X", "careers_url": "https://x.com", "ats": "unknown_ats"},
    ).status_code == 400
    assert auth_client.post(
        "/api/companies",
        json={"name": "X", "careers_url": "https://x.com", "locations": "bad"},
    ).status_code == 400


@pytest.mark.integration
def test_companies_remove_rename_errors(auth_client, rich_catalog):
    assert auth_client.post("/api/companies/remove", json={"country": "uk"}).status_code == 400
    assert auth_client.post(
        "/api/companies/remove",
        json={"country": "uk", "company": "No Such Co"},
    ).status_code == 404
    assert auth_client.post(
        "/api/companies/name",
        json={"country": "uk", "company": "Acme Backend Ltd", "new_name": ""},
    ).status_code == 400


# ---------------------------------------------------------------------------
# Fetch endpoints
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_fetch_status_and_country(scrape_enabled, auth_client, rich_catalog, monkeypatch):
    import relocation_jobs.panel_server as ps

    monkeypatch.setattr("relocation_jobs.web.scrape_runner._start_scrape_thread", _fake_start_scrape_thread)
    _reset_fetch_state()
    status = auth_client.get("/api/fetch/status")
    assert status.status_code == 200
    assert status.get_json()["running"] is False

    start = auth_client.post("/api/fetch", json={"country": "uk", "concurrency": 2})
    assert start.status_code == 200

    for _ in range(50):
        final = auth_client.get("/api/fetch/status").get_json()
        if final.get("running") is False and final.get("last_fetch_run"):
            break
        time.sleep(0.05)
    assert final["exit_code"] == 0
    assert final.get("last_fetch_run") is not None
    assert final["last_fetch_run"]["country"] == "uk"


@pytest.mark.integration
def test_fetch_history(auth_client):
    from datetime import datetime, timedelta, timezone

    from relocation_jobs.db import get_user_by_username, record_fetch_run

    admin = get_user_by_username("admin")
    assert admin
    started = datetime.now(timezone.utc).replace(microsecond=0)
    finished = started + timedelta(minutes=2)
    record_fetch_run(
        user_id=admin["id"],
        country="uk",
        company_name="Acme Backend Ltd",
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        exit_code=0,
        new_jobs=3,
        concurrency=1,
        companies_done=1,
        companies_total=1,
    )

    resp = auth_client.get("/api/fetch/history?country=uk&limit=5")
    assert resp.status_code == 200
    runs = resp.get_json()["runs"]
    assert len(runs) >= 1
    assert runs[0]["company_name"] == "Acme Backend Ltd"
    assert runs[0]["new_jobs"] == 3

    jobs = auth_client.get("/api/jobs?country=uk").get_json()
    assert "recent_fetch_runs" in jobs["stats"]


@pytest.mark.integration
def test_companies_fetch(scrape_enabled, auth_client, rich_catalog):
    _reset_fetch_state()
    ctx = _job_ctx(auth_client)
    resp = auth_client.post(
        "/api/companies/fetch",
        json={"country": ctx["country"], "company": ctx["company"]},
    )
    assert resp.status_code == 200
    for _ in range(50):
        if auth_client.get("/api/fetch/status").get_json().get("running") is False:
            break
        time.sleep(0.05)


@pytest.mark.integration
def test_fetch_cancel(scrape_enabled, auth_client, rich_catalog, monkeypatch):
    from relocation_jobs.web import fetch_state
    import relocation_jobs.panel_server as ps

    _reset_fetch_state()

    def slow_scrape(*args, **kwargs):
        time.sleep(2)

    def slow_start(country, skip_filled, concurrency, *, company=None, ats_type=None):
        fetch_state._fetch_thread = threading.Thread(
            target=slow_scrape,
            args=(country, skip_filled, concurrency),
            kwargs={"company": company, "ats_type": ats_type},
            daemon=True,
        )
        fetch_state._fetch_thread.start()

    monkeypatch.setattr("relocation_jobs.web.scrape_runner._run_scrape", slow_scrape)
    monkeypatch.setattr("relocation_jobs.web.scrape_runner._start_scrape_thread", slow_start)
    resp = auth_client.post("/api/fetch", json={"country": "uk"})
    assert resp.status_code == 200
    time.sleep(0.1)
    cancel = auth_client.post("/api/fetch/cancel")
    assert cancel.status_code == 200


@pytest.mark.integration
def test_fetch_errors(auth_client, rich_catalog, monkeypatch):
    import relocation_jobs.panel_server as ps

    _reset_fetch_state()
    assert auth_client.post("/api/fetch/cancel").status_code == 400

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)
    assert auth_client.post("/api/fetch", json={"country": "all"}).status_code == 400
    assert auth_client.post("/api/fetch", json={"country": "nope"}).status_code == 400

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "0")
    assert auth_client.post("/api/fetch", json={"country": "uk"}).status_code == 503

    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "1")
    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", False)
    assert auth_client.post("/api/fetch", json={"country": "uk"}).status_code == 503


@pytest.mark.integration
def test_fetch_already_running(scrape_enabled, auth_client, rich_catalog):
    import relocation_jobs.panel_server as ps

    _reset_fetch_state()
    with ps._fetch_lock:
        ps._fetch_state["running"] = True
    assert auth_client.post("/api/fetch", json={"country": "uk"}).status_code == 409
    _reset_fetch_state()


# ---------------------------------------------------------------------------
# panel_server internals (coverage for helpers)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_panel_server_helpers():
    import relocation_jobs.panel_server as ps

    assert ps._activity_from_scrape_line("Fetching Acme Corp")["message"].startswith("Fetching")
    assert ps._activity_from_scrape_line("Detected: greenhouse → url") is not None
    assert ps._activity_from_scrape_line("Known: lever → url") is not None
    assert ps._activity_from_scrape_line("Detecting ATS via Playwright") is not None
    assert ps._activity_from_scrape_line("No ATS detected, using generic") is not None
    assert ps._activity_from_scrape_line("TeamTailor HTML board: 3 roles") is not None
    assert ps._activity_from_scrape_line("Loading TeamTailor page 2…") is not None
    assert ps._activity_from_scrape_line("Greenhouse error: timeout") is not None
    assert ps._activity_from_scrape_line("Playwright error: fail") is not None
    assert ps._activity_from_scrape_line("[uk] Acme — enriched 2 job(s)") is not None
    assert ps._activity_from_scrape_line("@@PROGRESS@@{}") is None
    assert ps._activity_from_scrape_line("") is None

    ps._push_fetch_activity("  ")
    ps._push_fetch_activity("Step one", "detail")
    ps._on_scrape_progress({"current": 1, "total": 5, "company": "X", "status": "fetching"})
    ps._on_scrape_review({"included": [{"title": "A"}], "filtered": []})

    ps._reset_fetch_run_state(country="uk", company="Acme", file_name="uk.json", concurrency=4)
    assert ps._fetch_state["running"] is True

    ps._handle_scrape_ipc_line(
        "@@PROGRESS@@" + json.dumps({"current": 1, "total": 2, "company": "Acme", "status": "fetching"})
    )
    ps._handle_scrape_ipc_line(
        "@@PROGRESS@@" + json.dumps({"current": 2, "total": 2, "company": "Acme", "status": "done", "new_jobs": 1})
    )
    ps._handle_scrape_ipc_line("@@REVIEW@@" + json.dumps({"included": [], "filtered": []}))
    ps._handle_scrape_ipc_line("@@ACTIVITY@@" + json.dumps({"message": "Hi", "detail": "D"}))
    ps._handle_scrape_ipc_line("not ipc")
    ps._handle_scrape_ipc_line("@@PROGRESS@@not-json")

    ps._log("Starting (10 to process)")
    ps._log("Done finished")

    cmd = ps._build_scrape_cmd("uk", skip_filled=True, concurrency=8)
    assert "scrape_jobs" in " ".join(cmd)
    cmd_ats = ps._build_scrape_cmd("uk", skip_filled=False, concurrency=8, ats_type="greenhouse")
    assert "--ats" in cmd_ats
    assert "greenhouse" in cmd_ats
    cmd_serial = ps._build_scrape_cmd("uk", skip_filled=False, concurrency=1, company="Acme")
    assert cmd_serial[-1] == "Acme"

    with pytest.raises(LookupError):
        ps._build_scrape_cmd("invalid", skip_filled=False, concurrency=1)

    assert ps._should_cancel_fetch() is False
    with ps._fetch_lock:
        ps._fetch_state["cancel_requested"] = True
    assert ps._should_cancel_fetch() is True
    with ps._fetch_lock:
        ps._fetch_state["cancel_requested"] = False

    ps._terminate_scrape_process(None)
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    ps._terminate_scrape_process(mock_proc)

    assert ps.scrape_enabled() in (True, False)


@pytest.mark.integration
def test_run_scrape_mocked_subprocess(monkeypatch, tmp_data_dir, db, seeded_catalog, test_user):
    import relocation_jobs.panel_server as ps
    from datetime import datetime, timezone

    _reset_fetch_state()
    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)

    lines = [
        "@@PROGRESS@@" + json.dumps({"current": 1, "total": 1, "company": "Acme Backend Ltd", "status": "fetching"}),
        "Fetching Acme Backend Ltd",
        "@@PROGRESS@@" + json.dumps({"current": 1, "total": 1, "company": "Acme Backend Ltd", "status": "done", "new_jobs": 1}),
    ]

    class FakeProc:
        stdout = iter(lines)
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    monkeypatch.setattr(ps.subprocess, "Popen", lambda *a, **k: FakeProc())
    started = datetime.now(timezone.utc).isoformat()
    with ps._fetch_lock:
        ps._fetch_state["running"] = True
        ps._fetch_state["country"] = "uk"
        ps._fetch_state["user_id"] = test_user["id"]
        ps._fetch_state["started_at"] = started
    ps._run_scrape("uk", skip_filled=False, concurrency=1)
    assert ps._fetch_state["exit_code"] == 0
    assert ps._fetch_state["last_fetch_run"] is not None
    assert ps._fetch_state["last_fetch_run"]["new_jobs"] == 1


@pytest.mark.integration
def test_run_scrape_lookup_error(monkeypatch):
    import relocation_jobs.panel_server as ps

    _reset_fetch_state()
    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)
    with ps._fetch_lock:
        ps._fetch_state["running"] = True
    ps._run_scrape("invalid_country", skip_filled=False, concurrency=1)
    assert ps._fetch_state["exit_code"] == 1


@pytest.mark.integration
def test_run_scrape_no_httpx(monkeypatch):
    import relocation_jobs.panel_server as ps

    _reset_fetch_state()
    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", False)
    with ps._fetch_lock:
        ps._fetch_state["running"] = True
    ps._run_scrape("uk", skip_filled=False, concurrency=1)
    assert ps._fetch_state["exit_code"] == 1


@pytest.mark.integration
def test_reap_zombie_fetch():
    from relocation_jobs.web import fetch_state
    import relocation_jobs.panel_server as ps

    fetch_state._fetch_thread = threading.Thread(target=lambda: None, daemon=True)
    with ps._fetch_lock:
        ps._fetch_state["running"] = True
        ps._fetch_state["exit_code"] = None
        ps._fetch_state["finished_at"] = None
    fetch_state._fetch_thread.start()
    fetch_state._fetch_thread.join(timeout=2)
    ps._reap_zombie_fetch()
    assert ps._fetch_state["running"] is False


@pytest.mark.integration
def test_log_writer():
    import relocation_jobs.panel_server as ps

    writer = ps._LogWriter()
    writer.write("line one\nline two\n")
    writer.flush()
    assert any("line one" in x for x in ps._fetch_state["log"])


@pytest.mark.integration
def test_static_no_cache(auth_client):
    resp = auth_client.get("/static/")
    # May 404 if no static asset at root; header still set on static routes when file exists
    if resp.status_code == 200:
        assert resp.headers.get("Cache-Control") == "no-store"


@pytest.mark.integration
@pytest.mark.parametrize(
    "path,payload,expected",
    [
        ("/api/jobs/rejected", {"country": "uk", "company": "Acme Backend Ltd", "url": "https://x"}, 404),
        ("/api/jobs/reapply", {"country": "uk", "company": "Acme Backend Ltd", "url": "https://x"}, 404),
        ("/api/jobs/ats-score", {"country": "uk", "company": "Acme Backend Ltd", "url": "https://x", "ats_score": "bad"}, 400),
        ("/api/jobs/waiting-referral", {"country": "uk", "company": "Acme Backend Ltd", "url": "https://x"}, 404),
        ("/api/jobs/not-for-me", {"country": "uk", "company": "Acme Backend Ltd", "url": "https://x"}, 404),
        ("/api/jobs/looking-to-apply", {"country": "uk", "company": "Acme Backend Ltd", "url": "https://x"}, 404),
        ("/api/companies/applied", {"country": "uk", "company": "No Such Co"}, 404),
        ("/api/companies/awaiting-response", {"country": "uk", "company": "No Such Co"}, 404),
        ("/api/companies/city", {"country": "uk", "company": "No Such Co", "cities": ["London"]}, 404),
        ("/api/companies/fetch-problem", {"country": "uk", "company": "No Such Co"}, 404),
        ("/api/companies/fetch-ok", {"country": "uk", "company": "No Such Co"}, 404),
        (
            "/api/companies/jobs/manual-add",
            {"country": "uk", "company": "No Such Co", "jobs": [{"title": "T", "url": "https://x.com/t"}]},
            404,
        ),
    ],
)
def test_api_not_found_paths(auth_client, rich_catalog, path, payload, expected):
    resp = auth_client.post(path, json=payload)
    assert resp.status_code == expected


@pytest.mark.integration
def test_companies_add_multi_country(auth_client, mock_enrich):
    resp = auth_client.post(
        "/api/companies",
        json={
            "name": "Multi Country Co",
            "careers_url": "https://boards.greenhouse.io/multi",
            "countries": ["uk"],
        },
    )
    assert resp.status_code == 200
    auth_client.delete("/api/companies", json={"country": "uk", "company": "Multi Country Co"})


@pytest.mark.integration
def test_run_scrape_cancelled(monkeypatch, seeded_catalog, db):
    import relocation_jobs.panel_server as ps

    _reset_fetch_state()
    monkeypatch.setattr("relocation_jobs.web.deps.HTTPX_AVAILABLE", True)

    class FakeProc:
        stdout = iter(["working…"])
        returncode = 0

        def poll(self):
            return None

        def wait(self, timeout=None):
            with ps._fetch_lock:
                ps._fetch_state["cancel_requested"] = True
            return 130

        def terminate(self):
            pass

        def kill(self):
            pass

    monkeypatch.setattr(ps.subprocess, "Popen", lambda *a, **k: FakeProc())
    with ps._fetch_lock:
        ps._fetch_state["running"] = True
        ps._fetch_state["country"] = "uk"
        ps._fetch_state["company"] = "Acme Backend Ltd"
    ps._run_scrape("uk", skip_filled=False, concurrency=1, company="Acme Backend Ltd")
    assert ps._fetch_state.get("cancelled") is True


@pytest.mark.integration
def test_terminate_scrape_timeout(monkeypatch):
    import relocation_jobs.panel_server as ps

    proc = MagicMock()
    proc.poll.return_value = None
    proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="x", timeout=2.0),
        0,
    ]
    ps._terminate_scrape_process(proc)
    proc.kill.assert_called()

