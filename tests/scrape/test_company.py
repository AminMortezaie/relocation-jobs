from __future__ import annotations

import pytest

from relocation_jobs.scrape.company import process_company


@pytest.mark.asyncio
async def test_process_company_merges_and_counts_new():
    company = {
        "name": "Acme",
        "city": "London",
        "matching_jobs": [
            {"title": "Old Role", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"},
        ],
    }

    async def fetch_board(_client, _company, **kwargs):
        return [
            {"title": "Old Role", "url": "https://example.com/j/1?gh_jid=1"},
            {"title": "Backend Engineer", "url": "https://example.com/j/2?gh_jid=2"},
            {"title": "Marketing Manager", "url": "https://example.com/j/3?gh_jid=3"},
        ]

    line, new_count = await process_company(
        None, company, 1, 1, fetch_board=fetch_board, catalog_country="uk",
    )

    assert new_count == 1
    assert "1 new" in line
    assert company.get("fetch_ok") is True
    urls = {j["url"] for j in company["matching_jobs"]}
    assert "https://example.com/j/2?gh_jid=2" in urls
    assert "https://example.com/j/3?gh_jid=3" not in urls
    assert "https://example.com/j/1?gh_jid=1" in urls


@pytest.mark.asyncio
async def test_process_company_records_fetch_problem_on_error():
    company = {"name": "FailCo", "city": "Berlin", "matching_jobs": []}

    async def boom(_client, _company, **kwargs):
        raise RuntimeError("ATS down")

    line, new_count = await process_company(
        None, company, 1, 1, fetch_board=boom,
    )

    assert new_count == 0
    assert "Error:" in line
    assert company.get("fetch_problem") is True
    assert company.get("fetch_ok") is False
