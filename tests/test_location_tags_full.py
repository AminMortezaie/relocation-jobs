"""Location tag edge cases: filters, listing text, job board splits."""

import pytest

from relocation_jobs.location_tags import (
    city_matches,
    company_expected_locations,
    company_matches_location_filter,
    company_visible_for_country_filter,
    filter_jobs_by_expected_locations,
    format_location_display,
    job_listing_location_texts,
    job_matches_expected_locations,
    normalize_location,
    normalize_locations,
    sync_company_location_fields,
)


def test_city_matches_empty_filter():
    assert city_matches("London", "") is True
    assert city_matches("London", "london") is True
    assert city_matches("London", "Paris") is False


def test_normalize_locations_legacy_paths():
    locs = normalize_locations(None, catalog_country="uk", legacy_cities=["London", "London"])
    assert len(locs) == 1

    comma = normalize_locations(None, catalog_country="uk", legacy_city="London, Manchester")
    assert len(comma) == 2

    string_items = normalize_locations(["uk:London", "germany:Berlin"], catalog_country="uk")
    assert len(string_items) == 2


def test_sync_company_location_fields():
    company = {"city": "London", "cities": ["London"]}
    sync_company_location_fields(company, catalog_country="uk")
    assert company["locations"]
    assert "London" in company["city"]


def test_company_visible_for_country_filter():
    company = {
        "locations": [{"country": "germany", "city": "Berlin"}],
    }
    assert company_visible_for_country_filter(company, "all", catalog_country="uk") is True
    assert company_visible_for_country_filter(company, "", catalog_country="uk") is True
    assert company_visible_for_country_filter(company, "uk", catalog_country="uk") is True
    assert company_visible_for_country_filter(company, "germany", catalog_country="uk") is True
    assert company_visible_for_country_filter(company, "portugal", catalog_country="uk") is False


def test_company_matches_location_filter_no_match():
    company = {"locations": [{"country": "uk", "city": "London"}]}
    assert not company_matches_location_filter(company, "uk:Paris", catalog_country="uk")
    assert company_matches_location_filter(company, "", catalog_country="uk")


def test_job_listing_location_texts():
    job = {
        "location": "London, UK",
        "locations": [{"city": "London", "country": "United Kingdom"}],
        "url": "https://jobs.example.com/locations/london?city=London",
        "title": "Engineer – London",
    }
    texts = job_listing_location_texts(job)
    assert any("london" in t.casefold() for t in texts)

    dict_only = job_listing_location_texts({"locations": {"fullLocation": "Berlin, Germany"}})
    assert any("Berlin" in t for t in dict_only)

    list_loc = job_listing_location_texts({"locations": ["Paris", {"city": "Lyon"}]})
    assert len(list_loc) >= 2


def test_job_matches_unsupported_and_outside_country():
    expected = [{"country": "uk", "city": "London"}]
    usa_job = {"location": "Remote, USA"}
    ok, reason = job_matches_expected_locations(usa_job, expected)
    assert ok is False
    assert "unsupported country" in reason

    france_job = {"location": "Paris, France"}
    ok, reason = job_matches_expected_locations(france_job, expected)
    assert ok is False

    outside = {"location": "Berlin, Germany"}
    ok, reason = job_matches_expected_locations(outside, expected)
    assert ok is False
    assert "outside tagged" in reason


def test_job_matches_city_mismatch_and_unknown():
    expected = [{"country": "uk", "city": "London"}]
    mismatch = {"location": "Manchester, UK"}
    ok, reason = job_matches_expected_locations(mismatch, expected)
    assert ok is False
    assert reason == "city mismatch"

    unknown = {"title": "Mystery role"}
    ok, reason = job_matches_expected_locations(unknown, expected)
    assert ok is True
    assert reason is None


def test_job_matches_country_only_and_city_alias():
    expected = [{"country": "uk", "city": "London"}]
    country_only = {"location": "United Kingdom"}
    ok, reason = job_matches_expected_locations(country_only, expected)
    assert ok is True

    alias = {"location": "München, Germany"}
    expected_de = [{"country": "germany", "city": "Munich"}]
    ok, reason = job_matches_expected_locations(alias, expected_de)
    assert ok is True


def test_job_matches_no_expected():
    ok, reason = job_matches_expected_locations({"location": "Anywhere"}, [])
    assert ok is True
    assert reason is None


def test_filter_jobs_by_expected_locations():
    company = {
        "locations": [{"country": "uk", "city": "London"}],
        "city": "London (United Kingdom)",
    }
    jobs = [
        {"title": "Good", "location": "London, UK"},
        {"title": "Bad", "location": "Remote"},
        {"title": "USA", "location": "New York, USA"},
    ]
    included, excluded = filter_jobs_by_expected_locations(
        jobs, company, catalog_country="uk"
    )
    assert len(included) == 1
    assert included[0]["title"] == "Good"
    assert len(excluded) == 2
    reasons = {j["location_filter_reason"] for j in excluded}
    assert "remote only" in reasons

    all_in, none_out = filter_jobs_by_expected_locations(jobs, {"city": ""})
    assert all_in == jobs
    assert none_out == []


def test_job_matches_city_only_in_supported_country():
    expected = [{"country": "uk", "city": "London"}]
    job = {"location": "London"}
    ok, reason = job_matches_expected_locations(job, expected)
    assert ok is True
    assert reason is None


def test_job_matches_location_mismatch_fallback():
    expected = [{"country": "uk", "city": "London"}]
    job = {"location": "Somewhere vague"}
    ok, reason = job_matches_expected_locations(job, expected)
    assert ok is True
    assert reason is None


def test_format_location_display_empty_city():
    assert format_location_display("uk", "") == ""


def test_format_job_location_label_from_listing():
    from relocation_jobs.location_tags import format_job_location_label, job_location_fields

    assert format_job_location_label({"location": "Berlin, Germany"}) == "Berlin"
    assert format_job_location_label({
        "locations": [{"city": "Amsterdam", "country": "netherlands"}, "Rotterdam"],
    }) == "Amsterdam, Rotterdam"
    fields = job_location_fields({"location": "London, UK"})
    assert fields == {"location": "London, UK", "job_city": "London"}


def test_normalize_location_invalid_country():
    assert normalize_location("usa", "New York") is None

    company = {"cities": ["Berlin"], "city": "Berlin"}
    locs = company_expected_locations(company, catalog_country="germany")
    assert locs[0]["country"] == "germany"


def test_custom_cities_persist(tmp_data_dir):
    from relocation_jobs.location_tags import (
        add_custom_city,
        custom_cities_path,
        load_custom_cities,
        picker_cities_for_country,
    )

    loc = add_custom_city("uk", "Reading")
    assert loc == {
        "country": "uk",
        "city": "Reading",
        "key": "uk:reading",
        "country_label": "United Kingdom",
        "label": "Reading (United Kingdom)",
    }
    assert custom_cities_path().is_file()
    assert "Reading" in load_custom_cities()["uk"]
    assert "Reading" in picker_cities_for_country("uk")

    again = add_custom_city("uk", "reading")
    assert again["city"] == "Reading"
    assert load_custom_cities()["uk"].count("Reading") == 1


def test_add_custom_city_rejects_invalid_input(tmp_data_dir):
    from relocation_jobs.location_tags import add_custom_city, custom_cities_path

    with pytest.raises(ValueError, match="Invalid country or city"):
        add_custom_city("usa", "New York")
    with pytest.raises(ValueError, match="Invalid country or city"):
        add_custom_city("uk", "   ")
    assert not custom_cities_path().is_file()


def test_add_custom_city_does_not_persist_builtin_suggested(tmp_data_dir):
    from relocation_jobs.location_tags import (
        SUGGESTED_CITIES,
        add_custom_city,
        custom_cities_path,
        load_custom_cities,
    )

    loc = add_custom_city("uk", "london")
    assert loc["city"] == "London"
    assert loc["key"] == "uk:london"
    assert not custom_cities_path().is_file() or "uk" not in load_custom_cities()
    assert "London" in SUGGESTED_CITIES["uk"]


def test_picker_cities_for_country_merges_builtin_then_custom(tmp_data_dir):
    from relocation_jobs.location_tags import add_custom_city, picker_cities_for_country

    add_custom_city("germany", "Freiburg")
    merged = picker_cities_for_country("germany")
    assert merged[0] == "Berlin"
    assert "Freiburg" in merged
    assert merged.index("Freiburg") > merged.index("Berlin")


def test_tag_wrong_location_jobs():
    from relocation_jobs.location_tags import tag_wrong_location_jobs

    company = {"locations": [{"country": "germany", "city": "Berlin"}]}
    jobs = [
        {"title": "Local", "url": "https://example.com/local", "location": "Berlin, Germany"},
        {
            "title": "Remote abroad",
            "url": "https://example.com/tokyo",
            "location": "Tokyo, Japan",
        },
    ]
    tag_wrong_location_jobs(jobs, company, catalog_country="germany", tagged_date="2025-06-01")

    assert "not_for_me" not in jobs[0]
    assert jobs[1]["not_for_me"] is True
    assert jobs[1]["not_for_me_reason"] == "wrong_location"
    assert jobs[1]["not_for_me_date"] == "2025-06-01"

    tag_wrong_location_jobs(jobs, company, catalog_country="germany")
    assert "not_for_me" not in jobs[0]
    assert jobs[1]["not_for_me"] is True


def test_frankfurt_am_main_matches_frankfurt_office_tag():
    expected = [{"country": "germany", "city": "Frankfurt am Main"}]
    for loc in ("Frankfurt", "Frankfurt am Main", "Frankfurt, Germany"):
        ok, reason = job_matches_expected_locations({"location": loc}, expected)
        assert ok is True, f"{loc}: {reason}"

    expected_frankfurt = [{"country": "germany", "city": "Frankfurt"}]
    ok, reason = job_matches_expected_locations(
        {"location": "Frankfurt am Main, Germany"},
        expected_frankfurt,
    )
    assert ok is True, reason


def test_add_custom_city_treats_frankfurt_aliases_as_same(tmp_data_dir):
    from relocation_jobs.location_tags import add_custom_city, picker_cities_for_country

    loc = add_custom_city("germany", "Frankfurt am Main")
    assert loc["city"] in ("Frankfurt", "Frankfurt am Main")
    assert "Frankfurt am Main" in picker_cities_for_country("germany")
