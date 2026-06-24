from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from relocation_jobs.scrape.boards.workable import (
    fetch_workable_board,
    workable_jobs_api_url,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ats" / "workable.json"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_workable_board_parses_jobs():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.post(workable_jobs_api_url("acme")).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_workable_board(client, "https://apply.workable.com/acme/", {})
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Backend Software Engineer"
    assert jobs[0]["url"] == "https://apply.workable.com/acme/j/ABC123/"
    assert "Amsterdam" in jobs[0]["location"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_workable():
    from relocation_jobs.scrape.board import fetch_ats_board

    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.post(workable_jobs_api_url("acme")).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    company = {
        "name": "Acme",
        "ats_type": "workable",
        "ats_url": "https://apply.workable.com/acme/",
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert jobs[0]["title"] == "Backend Software Engineer"
