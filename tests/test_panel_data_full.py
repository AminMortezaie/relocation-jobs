"""Full panel_data coverage — public functions, filters, CRUD, helpers."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from relocation_jobs.catalog_db import save_country
from relocation_jobs.panel_data import (
    add_company,
    add_manual_jobs,
    compute_stats,
    detect_ats_for_company,
    detect_country_from_url,
    enrich_new_company,
    fetch_relocate_metadata,
    find_company_in_data,
    find_job_in_data,
    flatten_companies,
    flatten_jobs,
    list_ats_types,
    list_company_cities,
    list_company_locations,
    normalize_careers_url,
    normalize_company_size,
    now_iso,
    parse_company_cities,
    parse_country_from_location,
    remove_company,
    rename_company,
    resolve_company_name,
    resolve_country_key,
    set_company_applied,
    set_company_awaiting_response,
    set_company_fetch_ok,
    set_company_fetch_problem,
    set_job_applied,
    set_job_ats_score,
    set_job_looking_to_apply,
    set_job_not_for_me,
    set_job_reapply,
    set_job_rejected,
    set_job_seen,
    set_job_waiting_referral,
    today,
    touch_company_fetch_time,
    update_company_careers,
    update_company_city,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rich_catalog(seeded_catalog, sample_country_data):
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
    data["companies"].append(
        {
            "name": "Fetch OK Ltd",
            "city": "London",
            "careers_url": "https://example.co.uk/ok",
            "fetch_ok": True,
            "fetch_ok_date": "2025-06-01",
            "matching_jobs": [],
        }
    )
    save_country("uk", data)
    return data


def _acme_job(rich_catalog) -> tuple[str, str]:
    company = rich_catalog["companies"][0]["name"]
    url = rich_catalog["companies"][0]["matching_jobs"][0]["url"]
    return company, url


@pytest.fixture
def mock_external(monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.panel_data.fetch_relocate_metadata",
        lambda name, country_key=None: {
            "city": "London",
            "size": "51-200",
            "country": country_key or "uk",
        },
    )
    monkeypatch.setattr(
        "relocation_jobs.panel_data.detect_ats_for_company",
        lambda name, url, *, ats_hint=None: ("greenhouse", url),
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_today_now_iso():
    assert len(today()) == 10
    assert "T" in now_iso()


@pytest.mark.integration
def test_normalize_careers_url():
    assert normalize_careers_url("example.com/jobs").startswith("https://")
    with pytest.raises(ValueError):
        normalize_careers_url("")
    with pytest.raises(ValueError):
        normalize_careers_url("https://")


@pytest.mark.integration
def test_normalize_company_size():
    assert normalize_company_size("51 - 200") == "51-200"
    assert normalize_company_size("1,000+") == "1,000+"
    assert normalize_company_size("unknown") == ""


@pytest.mark.integration
def test_parse_country_and_url_hints():
    assert parse_country_from_location("Berlin, Germany") == "germany"
    assert parse_country_from_location("London, UK") == "uk"
    assert parse_country_from_location("") is None
    assert detect_country_from_url("https://careers.example.de/jobs") == "germany"
    assert detect_country_from_url("https://jobs.example.co.uk") == "uk"


@pytest.mark.integration
def test_resolve_country_key(mock_external):
    key, meta = resolve_country_key("Test Co", "https://boards.greenhouse.io/test", hint="uk")
    assert key == "uk"


@pytest.mark.integration
def test_list_ats_types():
    types = list_ats_types()
    assert isinstance(types, list)


# ---------------------------------------------------------------------------
# Load / find
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_find_company_and_job(rich_catalog):
    acme = rich_catalog["companies"][0]["name"]
    url = rich_catalog["companies"][0]["matching_jobs"][0]["url"]
    assert find_company_in_data(rich_catalog, acme) is not None
    assert find_company_in_data(rich_catalog, "missing") is None
    assert find_job_in_data(rich_catalog, acme, url) is not None
    assert find_job_in_data(rich_catalog, acme, "https://missing.example/job") is None


@pytest.mark.integration
def test_resolve_company_name_touch_fetch(rich_catalog):
    assert resolve_company_name("uk", "acme backend ltd") == "Acme Backend Ltd"
    ts = touch_company_fetch_time("uk", "Acme Backend Ltd")
    assert "T" in ts
    with pytest.raises(LookupError):
        touch_company_fetch_time("uk", "Missing Co")
    with pytest.raises(ValueError):
        touch_company_fetch_time("nope", "Acme Backend Ltd")


# ---------------------------------------------------------------------------
# flatten_companies filters
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"visa_only": True},
        {"hide_applied": True},
        {"hide_empty": True},
        {"not_applied_only": True},
        {"hide_position_applied": True},
        {"hide_position_rejected": True},
        {"position_applied_only": True},
        {"position_rejected_only": True},
        {"position_looking_to_apply_only": True},
        {"fetch_ok_only": True},
        {"fetch_problem_only": True},
        {"location": "London"},
        {"city": "Manchester"},
        {"country_key": None},
    ],
)
def test_flatten_companies_filters(rich_catalog, test_user, kwargs):
    uid = test_user["id"]
    companies, file_meta, fetch_problem_count = flatten_companies(
        kwargs.pop("country_key", "uk"),
        user_id=uid,
        **kwargs,
    )
    assert isinstance(companies, list)
    assert isinstance(file_meta, list)
    assert fetch_problem_count >= 0


@pytest.mark.integration
def test_flatten_hides_jobs_outside_office_tags(db, sample_country_data):
    company = sample_country_data["companies"][0]
    company["locations"] = [{"country": "uk", "city": "London"}]
    company["matching_jobs"] = [
        {
            "title": "Backend Engineer UK",
            "url": "https://example.com/jobs/uk",
            "location": "London, UK",
            "fetched": "2025-06-01",
        },
        {
            "title": "Backend Engineer DE",
            "url": "https://example.com/jobs/de",
            "location": "Berlin, Germany",
            "fetched": "2025-06-01",
        },
    ]
    save_country("uk", sample_country_data)

    companies, _, _ = flatten_companies("uk")
    acme = companies[0]

    assert len(acme["jobs"]) == 1
    assert acme["jobs"][0]["url"] == "https://example.com/jobs/uk"
    assert len(acme["not_for_me_jobs"]) == 1
    hidden = acme["not_for_me_jobs"][0]
    assert hidden["not_for_me"] is True
    assert hidden["not_for_me_reason"] == "wrong_location"
    assert hidden["job_city"] == "Berlin"


@pytest.mark.integration
def test_flatten_keeps_unknown_location_on_main_board(db, sample_country_data):
    company = sample_country_data["companies"][0]
    company["locations"] = [{"country": "uk", "city": "London"}]
    company["matching_jobs"] = [
        {
            "title": "Mystery Backend Engineer",
            "url": "https://example.com/jobs/unknown",
            "fetched": "2025-06-01",
        },
        {
            "title": "Backend Engineer DE",
            "url": "https://example.com/jobs/de",
            "location": "Berlin, Germany",
            "fetched": "2025-06-01",
        },
    ]
    save_country("uk", sample_country_data)

    companies, _, _ = flatten_companies("uk")
    acme = companies[0]
    assert len(acme["jobs"]) == 1
    assert acme["jobs"][0]["url"] == "https://example.com/jobs/unknown"
    assert len(acme["not_for_me_jobs"]) == 1


@pytest.mark.integration
def test_reconcile_wrong_location_restores_matching_job(db, sample_country_data, test_user):
    from relocation_jobs.panel_data import reconcile_wrong_location_hides, set_job_not_for_me

    uid = test_user["id"]
    company = sample_country_data["companies"][0]
    company_name = company["name"]
    company["locations"] = [{"country": "uk", "city": "London"}]
    job = {
        "title": "Backend Engineer UK",
        "url": "https://example.com/jobs/uk",
        "location": "London, UK",
        "fetched": "2025-06-01",
    }
    company["matching_jobs"] = [job]
    save_country("uk", sample_country_data)

    set_job_not_for_me(
        "uk",
        company_name,
        job["url"],
        user_id=uid,
        not_for_me=True,
        reason="wrong_location",
    )
    companies, _, _ = flatten_companies("uk", user_id=uid)
    assert companies[0]["jobs"] == []
    assert len(companies[0]["not_for_me_jobs"]) == 1

    restored = reconcile_wrong_location_hides(uid, country_key="uk", city_label="London")
    assert restored == 1

    companies, _, _ = flatten_companies("uk", user_id=uid)
    assert len(companies[0]["jobs"]) == 1
    assert companies[0]["not_for_me_jobs"] == []


@pytest.mark.integration
def test_flatten_companies_tracking_states(rich_catalog, test_user):
    uid = test_user["id"]
    company, url = _acme_job(rich_catalog)

    set_job_applied("uk", company, url, True, user_id=uid)
    set_job_rejected("uk", company, rich_catalog["companies"][0]["matching_jobs"][1]["url"], True, user_id=uid)
    set_job_looking_to_apply("uk", company, url, True, user_id=uid)
    set_job_seen("uk", company, url, True, user_id=uid)
    set_job_not_for_me("uk", company, rich_catalog["companies"][0]["matching_jobs"][1]["url"], user_id=uid, not_for_me=True)

    applied_only, _, _ = flatten_companies("uk", user_id=uid, position_applied_only=True)
    assert any(c["jobs"] for c in applied_only) or not applied_only

    rejected_only, _, _ = flatten_companies("uk", user_id=uid, position_rejected_only=True)
    assert isinstance(rejected_only, list)

    looking, _, _ = flatten_companies("uk", user_id=uid, position_looking_to_apply_only=True)
    assert isinstance(looking, list)


@pytest.mark.integration
def test_flatten_jobs(rich_catalog, test_user):
    jobs, file_meta = flatten_jobs("uk", user_id=test_user["id"])
    assert len(jobs) >= 2
    assert file_meta


@pytest.mark.integration
def test_compute_stats(rich_catalog, test_user):
    uid = test_user["id"]
    companies, file_meta, fetch_problem_count = flatten_companies("uk", user_id=uid)
    stats = compute_stats(
        companies,
        file_meta,
        fetch_problem_count=fetch_problem_count,
        user_id=uid,
        country_key="uk",
        timezone_name="Europe/London",
    )
    assert stats["total_jobs"] >= 2
    assert stats["fetch_problems"] >= 1
    assert "by_country" in stats
    assert stats["positions_applied_today"] >= 0


@pytest.mark.integration
def test_compute_stats_no_user(rich_catalog):
    companies, file_meta, fetch_problem_count = flatten_companies("uk")
    stats = compute_stats(companies, file_meta, fetch_problem_count=fetch_problem_count)
    assert stats["positions_applied_today"] == 0


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_locations_and_cities(rich_catalog):
    cities = list_company_cities("uk")
    assert "London" in cities or cities
    locs = list_company_locations("uk")
    assert locs
    picker = list_company_locations("uk", for_picker=True)
    assert picker
    all_locs = list_company_locations(None)
    assert all_locs

    acme = rich_catalog["companies"][0]
    parsed = parse_company_cities(acme, catalog_country="uk")
    assert isinstance(parsed, list)


@pytest.mark.integration
def test_list_company_locations_picker_includes_custom_cities(rich_catalog, tmp_data_dir):
    from relocation_jobs.location_tags import add_custom_city
    from relocation_jobs.panel_data import list_company_locations

    add_custom_city("uk", "Reading")

    picker = list_company_locations("uk", for_picker=True)
    keys = {loc["key"] for loc in picker}
    assert "uk:reading" in keys

    header = list_company_locations("uk", for_picker=False)
    header_keys = {loc["key"] for loc in header}
    assert "uk:reading" not in header_keys


# ---------------------------------------------------------------------------
# Job setters
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_set_job_applied_and_company_sync(rich_catalog, test_user):
    uid = test_user["id"]
    company, url = _acme_job(rich_catalog)
    result = set_job_applied("uk", company, url, True, user_id=uid)
    assert result["applied"] is True
    set_job_applied("uk", company, url, False, user_id=uid)
    with pytest.raises(LookupError):
        set_job_applied("uk", company, "https://missing.example/job", True, user_id=uid)


@pytest.mark.integration
def test_set_job_rejected_reapply(rich_catalog, test_user):
    uid = test_user["id"]
    company, url = _acme_job(rich_catalog)
    set_job_rejected("uk", company, url, True, user_id=uid)
    result = set_job_reapply("uk", company, url, user_id=uid)
    assert "rejected" in result or result is not None
    set_job_rejected("uk", company, url, False, user_id=uid)


@pytest.mark.integration
def test_set_job_waiting_referral(rich_catalog, test_user):
    uid = test_user["id"]
    company, url = _acme_job(rich_catalog)
    ok = set_job_waiting_referral(
        "uk",
        company,
        url,
        True,
        user_id=uid,
        linkedin_url="https://linkedin.com/in/tester",
    )
    assert ok["waiting_referral"] is True
    set_job_waiting_referral("uk", company, url, False, user_id=uid)
    with pytest.raises(ValueError):
        set_job_waiting_referral(
            "uk",
            company,
            url,
            True,
            user_id=uid,
            linkedin_url="https://evil.com/in/foo",
        )


@pytest.mark.integration
def test_set_job_ats_score(rich_catalog, test_user):
    uid = test_user["id"]
    company, url = _acme_job(rich_catalog)
    scored = set_job_ats_score("uk", company, url, 90, user_id=uid)
    assert scored["ats_score"] == 90
    cleared = set_job_ats_score("uk", company, url, None, user_id=uid)
    assert cleared["ats_score"] is None
    # Company exists but arbitrary URL still allowed for ATS score
    orphan = set_job_ats_score("uk", company, "https://example.com/orphan", 50, user_id=uid)
    assert orphan["ats_score"] == 50


@pytest.mark.integration
def test_set_job_looking_seen_not_for_me(rich_catalog, test_user):
    uid = test_user["id"]
    company, url = _acme_job(rich_catalog)
    assert set_job_looking_to_apply("uk", company, url, True, user_id=uid)["looking_to_apply"] is True
    assert set_job_seen("uk", company, url, True, user_id=uid)["seen"] is True
    nfm = set_job_not_for_me("uk", company, url, user_id=uid, not_for_me=True, reason="role")
    assert nfm["not_for_me"] is True
    set_job_not_for_me("uk", company, url, user_id=uid, not_for_me=False)


# ---------------------------------------------------------------------------
# Company setters & CRUD
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_set_company_applied_awaiting(rich_catalog, test_user):
    uid = test_user["id"]
    company = rich_catalog["companies"][0]["name"]
    assert set_company_applied("uk", company, True, user_id=uid)["company_applied"] is True
    assert set_company_awaiting_response("uk", company, True, user_id=uid)["awaiting_response"] is True
    set_company_applied("uk", company, False, user_id=uid)
    set_company_awaiting_response("uk", company, False, user_id=uid)
    with pytest.raises(LookupError):
        set_company_applied("uk", "Missing", True, user_id=uid)


@pytest.mark.integration
def test_set_company_fetch_flags(rich_catalog):
    company = rich_catalog["companies"][0]["name"]
    problem = set_company_fetch_problem("uk", company, True)
    assert problem["fetch_problem"] is True
    cleared = set_company_fetch_problem("uk", company, False, mark_fetch_ok=True)
    assert cleared["fetch_ok"] is True
    ok = set_company_fetch_ok("uk", company)
    assert ok["fetch_ok"] is True


@pytest.mark.integration
def test_add_rename_update_remove_company(rich_catalog, mock_external):
    added = add_company(
        "New Panel Co",
        "https://boards.greenhouse.io/newpanel",
        country_key="uk",
        ats_hint="greenhouse",
        locations=[{"country": "uk", "city": "Leeds"}],
    )
    assert added["name"] == "New Panel Co"

    renamed = rename_company("uk", "New Panel Co", "Renamed Panel Co")
    assert renamed["company"] == "Renamed Panel Co"

    careers = update_company_careers(
        "uk",
        "Renamed Panel Co",
        "https://boards.greenhouse.io/renamed",
        redetect_ats=True,
    )
    assert careers["careers_url"].endswith("/renamed")

    city = update_company_city("uk", "Renamed Panel Co", cities=["Leeds", "York"])
    assert city["cities"]

    city_str = update_company_city("uk", "Renamed Panel Co", cities="Bristol")
    assert city_str["city"]

    loc = update_company_city(
        "uk",
        "Renamed Panel Co",
        locations=[{"country": "uk", "city": "Cambridge"}],
    )
    assert loc["locations"]

    manual = add_manual_jobs(
        "uk",
        "Renamed Panel Co",
        [{"title": "Extra Role", "url": "https://example.com/extra-role-42"}],
    )
    assert manual["added"] == 1

    removed = remove_company("uk", "Renamed Panel Co")
    assert removed["company"] == "Renamed Panel Co"


@pytest.mark.integration
def test_add_company_duplicate(rich_catalog, mock_external):
    with pytest.raises(LookupError):
        add_company(
            "Acme Backend Ltd",
            "https://boards.greenhouse.io/acmebackend",
            country_key="uk",
        )


@pytest.mark.integration
def test_add_company_validation(mock_external):
    with pytest.raises(ValueError):
        add_company("", "https://example.com")
    with pytest.raises(ValueError):
        add_company("X", "https://")


@pytest.mark.integration
def test_rename_company_errors(rich_catalog, mock_external):
    with pytest.raises(ValueError):
        rename_company("uk", "Acme Backend Ltd", "Acme Backend Ltd")
    with pytest.raises(LookupError):
        rename_company("uk", "Missing Co", "Other")
    add_company(
        "Dup Target",
        "https://boards.greenhouse.io/dup",
        country_key="uk",
    )
    with pytest.raises(LookupError):
        rename_company("uk", "Acme Backend Ltd", "Dup Target")


@pytest.mark.integration
def test_manual_jobs_validation(rich_catalog):
    company = rich_catalog["companies"][0]["name"]
    with pytest.raises(ValueError):
        add_manual_jobs("uk", company, [])
    with pytest.raises(ValueError):
        add_manual_jobs("uk", company, [{"title": "", "url": ""}])
    with pytest.raises(LookupError):
        add_manual_jobs("uk", "Missing Co", [{"title": "T", "url": "https://example.com/t"}])


@pytest.mark.integration
def test_remove_company_not_found(rich_catalog):
    with pytest.raises(LookupError):
        remove_company("uk", "No Such Company")


@pytest.mark.integration
def test_resolve_country_key_from_url(mock_external, monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.panel_data.fetch_relocate_metadata",
        lambda *a, **k: {},
    )
    key, _ = resolve_country_key("Co", "https://jobs.example.nl/careers")
    assert key == "netherlands"


@pytest.mark.integration
def test_resolve_country_key_failure(monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.panel_data.fetch_relocate_metadata",
        lambda *a, **k: {},
    )
    with pytest.raises(ValueError):
        resolve_country_key("Co", "https://example.com/jobs")


@pytest.mark.integration
def test_fetch_relocate_metadata_mocked(monkeypatch):
    html = """
    <div class="company-location">London, UK</div>
    <div class="company-facts__heading">Company size</div>
    <div>51 - 200 employees</div>
    """

    class FakeResp:
        status_code = 200
        text = html

    monkeypatch.setattr("relocation_jobs.services.company_service.requests.get", lambda *a, **k: FakeResp())
    meta = fetch_relocate_metadata("Acme Backend Ltd")
    assert meta.get("city") == "London"
    assert meta.get("country") == "uk"


@pytest.mark.integration
def test_fetch_relocate_metadata_failures(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.RequestException("network")

    monkeypatch.setattr("relocation_jobs.services.company_service.requests.get", boom)
    assert fetch_relocate_metadata("Unknown Co") == {}


@pytest.mark.integration
def test_detect_ats_and_enrich(monkeypatch, mock_external):
    monkeypatch.setattr(
        "relocation_jobs.panel_data.detect_ats_for_company",
        lambda *a, **k: ("greenhouse", "https://boards.greenhouse.io/acme"),
    )
    ats_type, ats_url = detect_ats_for_company(
        "Acme",
        "https://boards.greenhouse.io/acme",
        ats_hint="greenhouse",
    )
    assert ats_type == "greenhouse"

    company = enrich_new_company(
        "Enriched Co",
        "https://boards.greenhouse.io/enriched",
        "uk",
        ats_hint="greenhouse",
    )
    assert company["name"] == "Enriched Co"
    assert company["careers_url"].startswith("https://")


@pytest.mark.integration
def test_flatten_without_user_id(rich_catalog):
    companies, _, _ = flatten_companies("uk")
    assert companies
    assert companies[0]["jobs"]


@pytest.mark.integration
def test_parse_country_location_suffix():
    assert parse_country_from_location("Remote, Portugal") == "portugal"
    assert parse_country_from_location("Office, NL") == "netherlands"

