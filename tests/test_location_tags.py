"""Location normalization and job/company filter matching."""

from relocation_jobs.location_tags import (
    company_matches_location_filter,
    format_location_display,
    job_matches_expected_locations,
    normalize_location,
    normalize_locations,
    parse_location_filter,
)


def test_normalize_location_from_catalog_country():
    loc = normalize_location("uk", "London")
    assert loc is not None
    assert loc["country"] == "uk"
    assert loc["city"] == "London"
    assert loc["key"] == "uk:london"


def test_normalize_locations_deduplicates():
    locs = normalize_locations(
        [
            {"country": "uk", "city": "London"},
            {"country": "uk", "city": "london"},
            {"country": "Germany", "city": "Berlin"},
        ],
        catalog_country="uk",
    )
    assert len(locs) == 2
    countries = {loc["country"] for loc in locs}
    assert countries == {"uk", "germany"}


def test_parse_location_filter():
    assert parse_location_filter("uk:London") == ("uk", "London")
    assert parse_location_filter("London") == (None, "London")
    assert parse_location_filter("") == (None, None)


def test_format_location_display():
    assert format_location_display("uk", "London") == "London (United Kingdom)"


def test_company_matches_location_filter():
    company = {
        "locations": [{"country": "uk", "city": "London"}],
        "city": "London",
    }
    assert company_matches_location_filter(company, "uk:London", catalog_country="uk")
    assert company_matches_location_filter(company, "London", catalog_country="uk")
    assert not company_matches_location_filter(company, "germany:Berlin", catalog_country="uk")


def test_job_matches_expected_locations():
    expected = [{"country": "uk", "city": "London"}]
    job = {"location": "London, UK", "title": "Backend Engineer"}
    include, reason = job_matches_expected_locations(job, expected)
    assert include is True
    assert reason is None

    remote_job = {"location": "Remote", "title": "Backend Engineer"}
    include, reason = job_matches_expected_locations(remote_job, expected)
    assert include is False
    assert reason == "remote only"
