from __future__ import annotations

from relocation_jobs.v2.catalog.repo import get_company
from relocation_jobs.v2.catalog.writes import save_company


def test_save_company_upserts_jobs(seeded_catalog_v2):
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
    save_company("uk", company)

    reloaded = get_company("uk", "Acme Backend Ltd")
    assert reloaded is not None
    assert len(reloaded["matching_jobs"]) == 3
    assert reloaded.get("fetch_ok") is True


def test_save_company_syncs_fetch_problem(seeded_catalog_v2):
    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    company["fetch_problem"] = True
    company["fetch_problem_date"] = "2025-06-03"
    company["fetch_ok"] = False
    save_company("uk", company)

    reloaded = get_company("uk", "Acme Backend Ltd")
    assert reloaded is not None
    assert reloaded.get("fetch_problem") is True
    assert reloaded.get("fetch_problem_date") == "2025-06-03"
