"""Catalog DB edge cases: migration, export, path helpers, upserts."""

from __future__ import annotations

import pytest

from relocation_jobs.catalog_db import (
    catalog_has_data,
    country_key_from_filename,
    load_country_catalog,
    save_country_catalog,
    touch_country_meta,
    upsert_companies,
    upsert_company,
)
from relocation_jobs.core.paths import data_dir


def test_country_key_from_filename():
    assert country_key_from_filename("uk_companies.json") == "uk"
    assert country_key_from_filename("/path/netherlands_companies.json") == "netherlands"
    assert country_key_from_filename("invalid.json") is None
    assert country_key_from_filename("") is None


@pytest.mark.integration
def test_touch_country_meta(db, sample_country_data):
    save_country_catalog("uk", sample_country_data)
    touch_country_meta("uk", updated="2025-07-01", total=5, jobs_fetched="2025-07-01")
    loaded = load_country_catalog("uk")
    assert loaded["updated"] == "2025-07-01"
    assert loaded["total"] == 5

    touch_country_meta("de", source="new-country", total=0)
    assert load_country_catalog("de") is not None

    touch_country_meta("uk", invalid_field="ignored")


@pytest.mark.integration
def test_upsert_company_and_batch(db, sample_country_data):
    save_country_catalog("uk", sample_country_data)

    upsert_company(
        "uk",
        {
            "name": "Upsert Co",
            "city": "Manchester",
            "cities": ["Manchester"],
            "matching_jobs": [
                {
                    "title": "Dev",
                    "url": "https://example.com/j/1?gh_jid=1",
                    "fetched": "2025-06-01",
                }
            ],
        },
    )
    loaded = load_country_catalog("uk")
    names = {c["name"] for c in loaded["companies"]}
    assert "Upsert Co" in names

    upsert_companies(
        "uk",
        [
            {
                "name": "Batch Co",
                "city": "Leeds",
                "matching_jobs": [],
            }
        ],
        touch_meta=True,
    )
    loaded = load_country_catalog("uk")
    assert any(c["name"] == "Batch Co" for c in loaded["companies"])

    upsert_companies("uk", [], touch_meta=False)


@pytest.mark.integration
def test_save_country_catalog_removes_absent_companies(db, sample_country_data):
    save_country_catalog("uk", sample_country_data)
    slim = {**sample_country_data, "companies": []}
    save_country_catalog("uk", slim)
    assert load_country_catalog("uk")["companies"] == []


@pytest.mark.integration
def test_upsert_skips_empty_company_name(db, sample_country_data):
    save_country_catalog("uk", sample_country_data)
    upsert_company("uk", {"name": "  ", "city": "Nowhere"})
    assert len(load_country_catalog("uk")["companies"]) == 1


@pytest.mark.integration
def test_company_sources_and_visa_parsing(db):
    save_country_catalog(
        "uk",
        {
            "source": "test",
            "companies": [
                {
                    "name": "Visa Co",
                    "city": "London",
                    "sources": ["relocate.me"],
                    "matching_jobs": [
                        {
                            "title": "Role",
                            "url": "https://example.com/v/1?gh_jid=1",
                            "visa_sponsorship": True,
                        },
                        {
                            "title": "No visa",
                            "url": "https://example.com/v/2?gh_jid=2",
                            "visa_sponsorship": False,
                        },
                    ],
                }
            ],
        },
    )
    company = load_country_catalog("uk")["companies"][0]
    assert company["sources"] == ["relocate.me"]
    jobs = {j["title"]: j for j in company["matching_jobs"]}
    assert jobs["Role"]["visa_sponsorship"] is True
    assert jobs["No visa"]["visa_sponsorship"] is False
