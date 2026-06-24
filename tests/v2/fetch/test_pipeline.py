from __future__ import annotations

import pytest

from relocation_jobs.v2.catalog.repo import get_company
from relocation_jobs.v2.fetch.repo import list_attempts
from relocation_jobs.v2.fetch.types import AttemptStatus


@pytest.mark.asyncio
async def test_fetch_and_persist_company_updates_catalog(seeded_catalog_v2):
    from relocation_jobs.v2.fetch.pipeline import fetch_and_persist_company

    async def fake_board(_client, company, **kwargs):
        return [
            {
                "title": "Backend Engineer",
                "url": "https://boards.greenhouse.io/acmebackend/jobs/555555?gh_jid=555555",
            },
        ]

    msg, new_count = await fetch_and_persist_company(
        None,
        "uk",
        "Acme Backend Ltd",
        fetch_board=fake_board,
    )
    assert new_count == 1
    assert "1 new" in msg

    company = get_company("uk", "Acme Backend Ltd")
    assert company is not None
    urls = {j["url"] for j in company["matching_jobs"]}
    assert "https://boards.greenhouse.io/acmebackend/jobs/555555?gh_jid=555555" in urls
    assert company.get("fetch_ok") is True

    attempts = list_attempts(country="uk", company_name="Acme Backend Ltd")
    assert len(attempts) == 1
    assert attempts[0].status == AttemptStatus.OK
    assert attempts[0].jobs_new == 1


@pytest.mark.asyncio
async def test_fetch_and_persist_unknown_company(db):
    from relocation_jobs.v2.fetch.pipeline import fetch_and_persist_company

    async def fake_board(_client, _company, **kwargs):
        return []

    with pytest.raises(LookupError):
        await fetch_and_persist_company(
            None,
            "uk",
            "Missing Co",
            fetch_board=fake_board,
        )
