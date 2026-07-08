from __future__ import annotations

from relocation_jobs.catalog.repo import get_company, sync_company_board_to_catalog
from relocation_jobs.panel.flatten import flatten_company, preview_board_company
from relocation_jobs.panel.service import load_context
from relocation_jobs.panel.types import FlattenFilters
from relocation_jobs.positions import set_job_not_for_me


def test_preview_board_company_matches_flatten_sort_key(seeded_catalog_v2):
    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    filters = FlattenFilters.from_kwargs(country_key="uk", user_id=1)
    ctx = load_context(1, "uk")
    preview = preview_board_company(
        company,
        country_key="uk",
        country_label="United Kingdom",
        filters=filters,
        ctx=ctx,
    )
    row = flatten_company(
        company,
        country_key="uk",
        country_label="United Kingdom",
        filters=filters,
        ctx=ctx,
    )
    assert preview is not None
    assert row is not None
    assert preview[0] == row["newest_job_fetched"]
    assert preview[1] == "uk"
    assert preview[2]["name"] == company["name"]


def test_preview_board_company_ignores_not_for_me_for_sort(seeded_catalog_v2):
    sync_company_board_to_catalog(
        "uk",
        {
            "name": "AAA Older Fetch",
            "city": "London",
            "size": "51-200",
            "careers_url": "https://boards.greenhouse.io/aaaolder",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/aaaolder",
            "matching_jobs": [
                {
                    "title": "Backend Engineer",
                    "url": "https://boards.greenhouse.io/aaaolder/jobs/1?gh_jid=1",
                    "fetched": "2025-06-02T00:45:00+00:00",
                    "last_seen": "2025-06-02T00:45:00+00:00",
                }
            ],
            "added": "2025-06-01",
        },
    )
    acme = get_company("uk", "Acme Backend Ltd")
    assert acme is not None
    jobs = list(acme.get("matching_jobs") or [])
    jobs.append(
        {
            "title": "Brand New Role",
            "url": "https://boards.greenhouse.io/acmebackend/jobs/999999?gh_jid=999999",
            "fetched": "2025-06-10T12:00:00+00:00",
            "last_seen": "2025-06-10T12:00:00+00:00",
        },
    )
    acme["matching_jobs"] = jobs
    sync_company_board_to_catalog("uk", acme)
    set_job_not_for_me(
        "uk",
        "Acme Backend Ltd",
        "https://boards.greenhouse.io/acmebackend/jobs/999999?gh_jid=999999",
        user_id=1,
        not_for_me=True,
    )

    filters = FlattenFilters.from_kwargs(country_key="uk", user_id=1)
    ctx = load_context(1, "uk")
    preview = preview_board_company(
        acme,
        country_key="uk",
        country_label="United Kingdom",
        filters=filters,
        ctx=ctx,
    )
    assert preview is not None
    assert preview[0].startswith("2025-06-01")
