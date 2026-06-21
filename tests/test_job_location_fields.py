"""Job listing location preserved through merge and API read."""

from __future__ import annotations

import pytest

from relocation_jobs.panel_data import _job_dict


@pytest.mark.integration
def test_job_dict_exposes_listing_city(seeded_catalog):
    job = {
        "title": "Backend Engineer",
        "url": "https://acme.example/jobs/backend",
        "location": "London, UK",
    }
    company = seeded_catalog["companies"][0]
    row = _job_dict(
        job,
        company_name=company["name"],
        company=company,
        key="uk",
        label="United Kingdom",
    )
    assert row["location"] == "London, UK"
    assert row["job_city"] == "London"


@pytest.mark.integration
def test_job_dict_omits_city_when_listing_has_no_location(seeded_catalog):
    job = {
        "title": "Mystery Engineer",
        "url": "https://acme.example/jobs/mystery",
    }
    company = seeded_catalog["companies"][0]
    row = _job_dict(
        job,
        company_name=company["name"],
        company=company,
        key="uk",
        label="United Kingdom",
    )
    assert "job_city" not in row
    assert "location" not in row
