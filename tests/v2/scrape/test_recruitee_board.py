from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from relocation_jobs.v2.scrape.boards.recruitee import (
    fetch_recruitee_board,
    recruitee_offers_api_url,
)

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "ats" / "recruitee.json"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_recruitee_board_parses_jobs():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.get(recruitee_offers_api_url("acme")).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_recruitee_board(client, "https://acme.recruitee.com/", {})
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Backend Developer"
    assert jobs[0]["location"] == "Amsterdam"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_recruitee():
    from relocation_jobs.v2.scrape.board import fetch_ats_board

    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.get(recruitee_offers_api_url("acme")).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    company = {
        "name": "Acme",
        "ats_type": "recruitee",
        "ats_url": "https://acme.recruitee.com/",
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert jobs[0]["title"] == "Backend Developer"
