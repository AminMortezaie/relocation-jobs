"""Admin aggregation helpers and dashboard data correctness."""

from __future__ import annotations

import copy

import pytest
from werkzeug.security import generate_password_hash

from relocation_jobs.admin_data import (
    _max_timestamp,
    get_admin_overview,
    get_catalog_overview,
    get_system_config,
)
from relocation_jobs.catalog_db import save_country, touch_country_meta
from relocation_jobs.db import (
    admin_tracking_totals,
    create_user,
    list_users_with_stats,
    record_fetch_run,
    user_count,
)
from relocation_jobs.panel_data import (
    compute_stats,
    flatten_companies,
    set_job_applied,
    set_job_rejected,
)


@pytest.fixture
def isolated_catalog(db):
    """Empty catalog tables so admin totals reflect only test seed data."""
    from relocation_jobs.db import db_transaction

    with db_transaction() as conn:
        conn.execute("DELETE FROM matching_jobs")
        conn.execute("DELETE FROM companies")
        conn.execute("DELETE FROM country_meta")
    yield


@pytest.fixture
def location_gated_catalog(isolated_catalog, sample_country_data):
    """UK catalog where one stored job fails the office location gate."""
    data = copy.deepcopy(sample_country_data)
    acme = data["companies"][0]
    acme["locations"] = [{"country": "uk", "city": "London"}]
    acme["matching_jobs"][0]["visa_sponsorship"] = True
    acme["matching_jobs"].append(
        {
            "title": "Wrong Location Engineer",
            "url": "https://boards.greenhouse.io/acmebackend/jobs/999999",
            "fetched": "2025-06-01",
            "last_seen": "2025-06-01",
            "location": "Berlin, Germany",
        }
    )
    save_country("uk", data, export_archive=False)
    return data


@pytest.fixture
def rich_catalog(isolated_catalog, sample_country_data):
    data = copy.deepcopy(sample_country_data)
    acme = data["companies"][0]
    acme["matching_jobs"][0]["visa_sponsorship"] = True
    acme["matching_jobs"][1]["visa_sponsorship"] = False
    data["companies"].append(
        {
            "name": "Empty Corp",
            "city": "Manchester",
            "locations": [{"country": "uk", "city": "Manchester"}],
            "careers_url": "https://example.co.uk/empty",
            "matching_jobs": [],
        }
    )
    data["companies"].append(
        {
            "name": "Fetch Problem Inc",
            "city": "London",
            "careers_url": "https://example.co.uk/problem",
            "fetch_problem": True,
            "fetch_problem_date": "2025-06-01",
            "matching_jobs": [],
        }
    )
    save_country("uk", data, export_archive=False)
    return data


def test_max_timestamp_picks_latest():
    assert _max_timestamp("2026-06-02", "2026-06-21", "2026-06-19T11:38:02+00:00") == (
        "2026-06-21"
    )
    assert _max_timestamp("2026-06-02", "2026-06-19T11:38:02+00:00") == (
        "2026-06-19T11:38:02+00:00"
    )


def test_max_timestamp_ignores_catalog_import_date():
    assert _max_timestamp("2026-06-02") == "2026-06-02"
    assert _max_timestamp("", None, "2026-06-20T10:00:00+00:00") == (
        "2026-06-20T10:00:00+00:00"
    )


@pytest.mark.integration
def test_catalog_last_fetch_not_catalog_import_date(isolated_catalog, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)
    touch_country_meta(
        "uk",
        fetched="2026-06-02",
        updated="2026-06-20",
        jobs_fetched="2026-06-20T10:00:00+00:00",
    )
    meta = next(m for m in get_catalog_overview()["country_meta"] if m["country"] == "uk")
    assert meta["catalog_imported"] == "2026-06-02"
    assert meta["last_fetch"] == "2026-06-20T10:00:00+00:00"


@pytest.mark.integration
def test_catalog_last_fetch_ignores_catalog_updated_field(isolated_catalog, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)
    touch_country_meta("uk", jobs_fetched="", updated="2026-06-21")
    meta = next(m for m in get_catalog_overview()["country_meta"] if m["country"] == "uk")
    assert meta["last_fetch"] == "2025-06-01"


@pytest.mark.integration
def test_catalog_last_fetch_uses_latest_job_when_meta_cleared(isolated_catalog, location_gated_catalog):
    touch_country_meta("uk", jobs_fetched="")
    meta = next(m for m in get_catalog_overview()["country_meta"] if m["country"] == "uk")
    assert meta["last_fetch"] == "2025-06-01"


@pytest.mark.integration
def test_catalog_job_counts_match_panel_visible(isolated_catalog, location_gated_catalog):
    companies, file_meta, fetch_problem_count = flatten_companies("uk", user_id=None)
    stats = compute_stats(companies, file_meta, fetch_problem_count=fetch_problem_count)
    overview = get_catalog_overview()
    uk = next(c for c in overview["countries"] if c["country"] == "uk")

    assert uk["stored_jobs"] == 3
    assert uk["jobs"] == stats["total_jobs"] == 2
    assert uk["visa_jobs"] == stats["visa_sponsored"] == 1
    assert overview["totals"]["jobs"] == 2
    assert overview["totals"]["stored_jobs"] == 3


@pytest.mark.integration
def test_catalog_fetch_problems_match_panel(isolated_catalog, rich_catalog):
    _, _, fetch_problem_count = flatten_companies("uk", user_id=None)
    overview = get_catalog_overview()
    uk = next(c for c in overview["countries"] if c["country"] == "uk")

    assert uk["fetch_problems"] == fetch_problem_count == 1
    assert overview["totals"]["fetch_problems"] == 1
    assert len(overview["fetch_problem_companies"]) == 1
    assert overview["fetch_problem_companies"][0]["name"] == "Fetch Problem Inc"


@pytest.mark.integration
def test_catalog_empty_companies_count(isolated_catalog, rich_catalog):
    overview = get_catalog_overview()
    assert overview["totals"]["empty_companies"] == 2


@pytest.mark.integration
def test_catalog_country_meta_total_uses_live_company_count(isolated_catalog, rich_catalog):
    touch_country_meta("uk", total=999)
    meta = next(m for m in get_catalog_overview()["country_meta"] if m["country"] == "uk")
    assert meta["total"] == 3


@pytest.mark.integration
def test_catalog_country_meta_includes_countries_without_meta_row(isolated_catalog, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)
    from relocation_jobs.db import get_connection

    get_connection().execute("DELETE FROM country_meta WHERE country = 'uk'")
    overview = get_catalog_overview()
    meta = next(m for m in overview["country_meta"] if m["country"] == "uk")
    assert meta["total"] == 1
    assert meta["last_fetch"] == "2025-06-01"


@pytest.mark.integration
def test_catalog_by_ats_counts(isolated_catalog, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)
    overview = get_catalog_overview()
    greenhouse = next(row for row in overview["by_ats"] if row["ats_type"] == "greenhouse")
    assert greenhouse["companies"] == 1


@pytest.mark.integration
def test_admin_overview_user_and_catalog_totals(isolated_catalog, rich_catalog, test_user):
    overview = get_admin_overview()
    catalog = get_catalog_overview()

    assert overview["users"] == user_count()
    assert overview["users"] >= 1
    assert overview["catalog"]["companies"] == catalog["totals"]["companies"]
    assert overview["catalog"]["jobs"] == catalog["totals"]["jobs"]
    assert overview["fetch"]["running"] is False


@pytest.mark.integration
def test_admin_tracking_totals_match_user_stats(db, rich_catalog, test_user):
    company = "Acme Backend Ltd"
    url = "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456"
    uid = test_user["id"]
    set_job_applied("uk", company, url, True, user_id=uid)
    set_job_rejected(
        "uk",
        company,
        "https://boards.greenhouse.io/acmebackend/jobs/789012?gh_jid=789012",
        True,
        user_id=uid,
    )

    totals = admin_tracking_totals()
    users = list_users_with_stats()
    user_row = next(u for u in users if u["id"] == test_user["id"])

    assert totals["tracking_rows"] == sum(u["tracking_rows"] for u in users)
    assert totals["applied_positions"] == sum(u["applied_positions"] for u in users) == 1
    assert totals["rejected_positions"] == sum(u["rejected_positions"] for u in users) == 1
    assert user_row["applied_positions"] == 1
    assert user_row["rejected_positions"] == 1


@pytest.mark.integration
def test_list_users_marks_env_admin_when_flag_missing(db, monkeypatch):
    monkeypatch.setenv("PANEL_ADMIN_USER", "legacyadmin")
    create_user("legacyadmin", generate_password_hash("legacypass12"), is_admin=False)

    admin_user = next(u for u in list_users_with_stats() if u["username"] == "legacyadmin")
    assert admin_user["is_admin"] is True


@pytest.mark.integration
def test_system_config_shape(db, monkeypatch):
    monkeypatch.setenv("PANEL_ALLOW_REGISTER", "1")
    config = get_system_config(scrape_enabled=False, httpx_available=True)

    assert config["database"] == "sqlite"
    assert config["scrape_enabled"] is False
    assert config["allow_register"] is True
    assert config["httpx_available"] is True
    assert isinstance(config["include_keywords"], list)
    assert config["known_ats_count"] > 0
    assert "uk" in {c["id"] for c in config["countries"]}


@pytest.mark.integration
def test_catalog_visible_counts_fallback_on_load_error(
    isolated_catalog, sample_country_data, monkeypatch,
):
    save_country("uk", sample_country_data, export_archive=False)

    def _boom(_key, user_id=None):
        raise IndexError("tuple index out of range")

    monkeypatch.setattr(
        "relocation_jobs.panel_data.flatten_companies",
        _boom,
    )
    overview = get_catalog_overview()
    uk = next(c for c in overview["countries"] if c["country"] == "uk")
    assert uk["jobs"] == uk["stored_jobs"] == 2


@pytest.mark.integration
def test_fetch_run_recorded_fields(db, test_user):
    run = record_fetch_run(
        user_id=test_user["id"],
        country="uk",
        company_name=None,
        started_at="2026-06-21T10:00:00+00:00",
        finished_at="2026-06-21T10:05:30+00:00",
        exit_code=0,
        new_jobs=4,
        concurrency=8,
        companies_done=3,
        companies_total=3,
        result_line="Done uk",
    )
    assert run["scope"] == "country"
    assert run["duration_seconds"] == 330
    assert run["new_jobs"] == 4
