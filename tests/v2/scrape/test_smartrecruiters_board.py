from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from relocation_jobs.v2.scrape.boards.smartrecruiters import (
    fetch_smartrecruiters_board,
    smartrecruiters_postings_page_url,
)

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "ats" / "smartrecruiters.json"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_smartrecruiters_board_parses_jobs():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.get(smartrecruiters_postings_page_url("Acme", 0)).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_smartrecruiters_board(
            client,
            "https://jobs.smartrecruiters.com/Acme",
            {},
        )
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Java Backend Engineer"
    assert jobs[0]["location"] == "Berlin, Germany"
    assert jobs[0]["url"].endswith("/job-001")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_smartrecruiters():
    from relocation_jobs.v2.scrape.board import fetch_ats_board

    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.get(smartrecruiters_postings_page_url("Acme", 0)).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    company = {
        "name": "Acme",
        "ats_type": "smartrecruiters",
        "ats_url": "https://jobs.smartrecruiters.com/Acme",
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert jobs[0]["title"] == "Java Backend Engineer"
