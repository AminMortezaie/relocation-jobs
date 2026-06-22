"""Catalog DB round-trip: companies and jobs persist correctly."""

import pytest

from relocation_jobs.catalog_db import catalog_has_data, load_country, save_country


@pytest.mark.integration
def test_save_and_load_country(seeded_catalog, sample_country_data):
    assert catalog_has_data()
    loaded = load_country("uk")
    assert loaded is not None
    assert loaded["source"] == sample_country_data["source"]
    assert len(loaded["companies"]) == 1

    company = loaded["companies"][0]
    assert company["name"] == "Acme Backend Ltd"
    assert company["ats_type"] == "greenhouse"
    assert len(company["matching_jobs"]) == 2
    assert all(j.get("idempotency_key") for j in company["matching_jobs"])


@pytest.mark.integration
def test_save_country_updates_meta_total(db, sample_country_data):
    save_country("uk", sample_country_data)
    loaded = load_country("uk")
    assert loaded["total"] == 1

    sample_country_data["companies"].append(
        {
            "name": "Second Co",
            "city": "Manchester",
            "matching_jobs": [],
        }
    )
    save_country("uk", sample_country_data)
    loaded = load_country("uk")
    assert len(loaded["companies"]) == 2


@pytest.mark.integration
def test_matching_job_location_round_trips_through_catalog(db, sample_country_data):
    company = sample_country_data["companies"][0]
    job = company["matching_jobs"][0]
    job["location"] = "Berlin, Germany"
    job["locations"] = [{"city": "Berlin", "country": "Germany"}]

    save_country("uk", sample_country_data)
    loaded = load_country("uk")
    stored = loaded["companies"][0]["matching_jobs"][0]

    assert stored["location"] == "Berlin, Germany"
    assert stored["locations"] == [{"city": "Berlin", "country": "Germany"}]

    job["location"] = ""
    job.pop("locations", None)
    save_country("uk", sample_country_data)
    reloaded = load_country("uk")
    preserved = reloaded["companies"][0]["matching_jobs"][0]
    assert preserved["location"] == "Berlin, Germany"
    assert preserved["locations"] == [{"city": "Berlin", "country": "Germany"}]
