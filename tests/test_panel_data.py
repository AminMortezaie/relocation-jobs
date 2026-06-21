"""Panel business logic: flatten, stats, company CRUD."""

import pytest

from relocation_jobs.panel_data import (
    add_company,
    compute_stats,
    flatten_companies,
    remove_company,
    set_job_applied,
)


@pytest.mark.integration
def test_flatten_companies_from_catalog(seeded_catalog, test_user):
    companies, file_meta, _fetch_problem_count = flatten_companies("uk", user_id=test_user["id"])
    assert len(companies) == 1
    assert companies[0]["name"] == "Acme Backend Ltd"
    assert companies[0]["job_count"] == 2
    assert len(file_meta) == 1


@pytest.mark.integration
def test_flatten_hides_applied_jobs(seeded_catalog, test_user):
    uid = test_user["id"]
    url = "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456"
    set_job_applied("uk", "Acme Backend Ltd", url, True, user_id=uid)

    visible, _, _ = flatten_companies("uk", user_id=uid, hide_position_applied=True)
    visible_urls = {j["url"] for c in visible for j in c["jobs"]}
    assert url not in visible_urls

    all_jobs, _, _ = flatten_companies("uk", user_id=uid)
    all_urls = {j["url"] for c in all_jobs for j in c["jobs"]}
    assert url in all_urls


@pytest.mark.integration
def test_compute_stats(seeded_catalog, test_user):
    companies, file_meta, fetch_problem_count = flatten_companies("uk", user_id=test_user["id"])
    stats = compute_stats(
        companies,
        file_meta,
        fetch_problem_count=fetch_problem_count,
        user_id=test_user["id"],
        country_key="uk",
    )
    assert stats["total_jobs"] >= 2


@pytest.mark.integration
def test_add_and_remove_company(seeded_catalog, monkeypatch):
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

    monkeypatch.setattr("relocation_jobs.panel_data.enrich_new_company", fake_enrich)

    add_company(
        "Temp Corp",
        "https://boards.greenhouse.io/temp",
        country_key="uk",
    )
    companies, _, _ = flatten_companies("uk")
    names = {c["name"] for c in companies}
    assert "Temp Corp" in names

    remove_company("uk", "Temp Corp")
    companies, _, _ = flatten_companies("uk")
    names = {c["name"] for c in companies}
    assert "Temp Corp" not in names
