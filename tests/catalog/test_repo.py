from __future__ import annotations

import pytest

from relocation_jobs.core.job_identity import job_idempotency_key
from relocation_jobs.catalog.repo import (
    get_company,
    get_job_by_url,
    list_country_company_stubs,
    load_country_catalog,
    sync_company_board_to_catalog,
)
from relocation_jobs.catalog.writes import upsert_company


def test_sync_company_board_appends_job(seeded_catalog_v2):
    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    jobs = list(company["matching_jobs"])
    jobs.append(
        {
            "title": "Backend Engineer",
            "url": "https://boards.greenhouse.io/acmebackend/jobs/999999?gh_jid=999999",
            "fetched": "2025-06-02",
            "last_seen": "2025-06-02",
        }
    )
    company["matching_jobs"] = jobs
    company["fetch_ok"] = True
    company["fetch_ok_date"] = "2025-06-02"
    sync_company_board_to_catalog("uk", company)

    reloaded = get_company("uk", "Acme Backend Ltd")
    assert reloaded is not None
    assert len(reloaded["matching_jobs"]) == 3
    assert reloaded.get("fetch_ok") is True


def test_sync_company_board_persists_fetch_problem_flags(seeded_catalog_v2):
    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    company["fetch_problem"] = True
    company["fetch_problem_date"] = "2025-06-03"
    company["fetch_ok"] = False
    sync_company_board_to_catalog("uk", company)

    reloaded = get_company("uk", "Acme Backend Ltd")
    assert reloaded is not None
    assert reloaded.get("fetch_problem") is True
    assert reloaded.get("fetch_problem_date") == "2025-06-03"


def test_sync_company_board_persists_description_text(seeded_catalog_v2):
    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    jobs = list(company["matching_jobs"])
    jobs[0]["description_text"] = "We are hiring a senior backend engineer with Go experience."
    company["matching_jobs"] = jobs
    sync_company_board_to_catalog("uk", company)

    reloaded = get_company("uk", "Acme Backend Ltd")
    assert reloaded is not None
    match = next(j for j in reloaded["matching_jobs"] if j["url"] == jobs[0]["url"])
    assert match["description_text"] == jobs[0]["description_text"]


def test_get_job_by_url_prefers_exact_match_within_company(seeded_catalog_v2):
    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    url_a = company["matching_jobs"][0]["url"]
    url_b = company["matching_jobs"][1]["url"]
    alias = f"{url_a}&utm_source=linkedin"

    assert get_job_by_url(alias, company_name="Acme Backend Ltd", country_key="uk")["url"] == url_a
    assert get_job_by_url(url_b, company_name="Acme Backend Ltd", country_key="uk")["url"] == url_b
    assert job_idempotency_key(alias) == job_idempotency_key(url_a)
    assert job_idempotency_key(url_a) != job_idempotency_key(url_b)


@pytest.mark.fresh_db
def test_custom_country_catalog_without_meta(db, tmp_data_dir):
    from relocation_jobs.core.location_tags import add_custom_country

    add_custom_country("Armenia")
    upsert_company(
        "armenia",
        {
            "name": "Armenia Fetch Co",
            "careers_url": "https://example.com/careers",
            "ats_type": "greenhouse",
            "matching_jobs": [],
            "sources": ["panel"],
        },
    )

    stubs = list_country_company_stubs("armenia")
    assert [item["name"] for item in stubs] == ["Armenia Fetch Co"]

    catalog = load_country_catalog("armenia")
    assert catalog is not None
    assert len(catalog["companies"]) == 1
    assert catalog["total"] == 1
