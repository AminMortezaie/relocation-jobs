from __future__ import annotations

from relocation_jobs.core.location_tags import (
    company_expected_locations,
    job_fails_office_location_gate,
    job_matches_expected_locations,
    sync_company_location_fields,
)


def _berlin_company() -> dict:
    company = {
        "name": "Tagged Co",
        "cities": ["Berlin"],
        "locations": [{"country": "germany", "city": "Berlin"}],
        "matching_jobs": [],
    }
    sync_company_location_fields(company, catalog_country="germany")
    return company


def _expected(company: dict) -> list[dict]:
    return company_expected_locations(company, catalog_country="germany")


def test_unparsed_foreign_city_fails_berlin_tag():
    company = _berlin_company()
    expected = _expected(company)
    for loc in ("Paris", "Bordeaux", "Barcelona", "Tokyo"):
        ok, reason = job_matches_expected_locations({"location": loc}, expected)
        assert ok is False, loc
        assert reason == "location mismatch"


def test_berlin_listing_passes_berlin_tag():
    company = _berlin_company()
    expected = _expected(company)
    for loc in ("Berlin", "Berlin, Germany"):
        ok, _ = job_matches_expected_locations({"location": loc}, expected)
        assert ok is True, loc


def test_us_state_listings_fail_berlin_tag():
    company = _berlin_company()
    expected = _expected(company)
    for loc in (
        "Palo Alto, CA",
        "New York, NY",
        "Boston, MA",
        "Palo Alto, CA or San Francisco, CA",
    ):
        ok, reason = job_matches_expected_locations({"location": loc}, expected)
        assert ok is False, loc
        assert "usa" in (reason or "")


def test_india_listing_fails_berlin_tag():
    company = _berlin_company()
    expected = _expected(company)
    ok, reason = job_matches_expected_locations({"location": "Bengaluru, IN"}, expected)
    assert ok is False
    assert "india" in (reason or "")


def test_no_office_tags_skips_gate():
    company = {"name": "Untagged", "cities": [], "locations": []}
    fails, reason = job_fails_office_location_gate(
        {"location": "Paris"}, company, catalog_country="germany",
    )
    assert fails is False
    assert reason is None


def test_empty_location_keeps_benefit_of_doubt():
    company = _berlin_company()
    ok, _ = job_matches_expected_locations({"location": ""}, _expected(company))
    assert ok is True


def test_title_team_suffix_without_location_is_not_a_gate():
    company = _berlin_company()
    ok, _ = job_matches_expected_locations(
        {"title": "Senior Software Engineer - PayOut & Fraud"},
        _expected(company),
    )
    assert ok is True


def test_custom_catalog_country_is_not_treated_as_unsupported(monkeypatch):
    import relocation_jobs.core.location_tags as mod

    labels = {
        "germany": "Germany",
        "netherlands": "Netherlands",
        "uk": "United Kingdom",
        "portugal": "Portugal",
        "sweden": "Sweden",
    }
    monkeypatch.setattr(mod, "all_country_labels", lambda: labels)
    company = {
        "name": "Evolution",
        "cities": ["Stockholm"],
        "locations": [{"country": "sweden", "city": "Stockholm"}],
        "matching_jobs": [],
    }
    sync_company_location_fields(company, catalog_country="sweden")
    expected = company_expected_locations(company, catalog_country="sweden")
    ok, reason = job_matches_expected_locations(
        {"location": "Stockholm, Stockholm County, Sweden"},
        expected,
    )
    assert ok is True, reason
    ok_demonym, reason_demonym = job_matches_expected_locations(
        {"location": "Swedish"},
        expected,
    )
    assert ok_demonym is True, reason_demonym
    ok_fr, reason_fr = job_matches_expected_locations(
        {"location": "Paris, France"},
        expected,
    )
    assert ok_fr is False
    assert "france" in (reason_fr or "")


def test_non_denylist_custom_country_matches_by_label(monkeypatch):
    import relocation_jobs.core.location_tags as mod

    labels = {
        "germany": "Germany",
        "netherlands": "Netherlands",
        "uk": "United Kingdom",
        "portugal": "Portugal",
        "georgia": "Georgia",
    }
    monkeypatch.setattr(mod, "all_country_labels", lambda: labels)
    company = {
        "name": "TBC Bank",
        "cities": ["Tbilisi"],
        "locations": [{"country": "georgia", "city": "Tbilisi"}],
        "matching_jobs": [],
    }
    sync_company_location_fields(company, catalog_country="georgia")
    expected = company_expected_locations(company, catalog_country="georgia")
    ok, reason = job_matches_expected_locations(
        {"location": "Tbilisi, Georgia"},
        expected,
    )
    assert ok is True, reason
    ok_de, reason_de = job_matches_expected_locations(
        {"location": "Berlin, Germany"},
        expected,
    )
    assert ok_de is False
    assert "germany" in (reason_de or "") or "outside tagged" in (reason_de or "")
