from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from relocation_jobs.scrape.boards.ashby import (
    ashby_job_board_api_url,
    fetch_ashby_board,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ats" / "ashby.json"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ashby_board_parses_jobs():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.get(ashby_job_board_api_url("acme")).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_ashby_board(client, "https://jobs.ashbyhq.com/acme", {})
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Senior Backend Engineer"
    assert jobs[0]["location"] == "Berlin, Germany"
    assert jobs[0]["url"].endswith("eeeeeeeeeeee")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ashby_board_skips_empty_title():
    respx.get(ashby_job_board_api_url("acme")).mock(
        return_value=Response(
            200,
            json={
                "jobs": [
                    {
                        "title": "",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/x",
                        "location": "Berlin",
                    },
                ],
            },
        ),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_ashby_board(client, "https://jobs.ashbyhq.com/acme", {})
    assert jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ashby_board_playwright_fallback():
    respx.get(ashby_job_board_api_url("acme")).mock(
        return_value=Response(500, text="error"),
    )
    import httpx

    def fake_playwright(url: str) -> list[dict]:
        assert url == "https://jobs.ashbyhq.com/acme"
        return [{"title": "Backend Engineer", "url": "https://jobs.ashbyhq.com/acme/j/1"}]

    async with httpx.AsyncClient() as client:
        jobs = await fetch_ashby_board(
            client,
            "https://jobs.ashbyhq.com/acme",
            {},
            playwright_fallback=fake_playwright,
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Backend Engineer"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_ashby():
    from relocation_jobs.scrape.board import fetch_ats_board

    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    respx.get(ashby_job_board_api_url("acme")).mock(
        return_value=Response(200, json=payload),
    )
    import httpx

    company = {
        "name": "Acme",
        "ats_type": "ashby",
        "ats_url": "https://jobs.ashbyhq.com/acme",
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Senior Backend Engineer"
