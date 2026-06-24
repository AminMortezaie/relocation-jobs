from __future__ import annotations

import pytest
import respx
from httpx import Response

from relocation_jobs.scrape.boards.lever import (
    fetch_lever_board,
    lever_postings_api_url,
)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_lever_board_parses_jobs():
    respx.get(lever_postings_api_url("acme", ats_url="https://jobs.lever.co/acme")).mock(
        return_value=Response(
            200,
            json=[
                {
                    "text": "Senior Backend Engineer",
                    "hostedUrl": "https://jobs.lever.co/acme/backend",
                    "categories": {"location": "London"},
                },
                {"text": "", "hostedUrl": "https://jobs.lever.co/acme/empty"},
            ],
        ),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_lever_board(client, "https://jobs.lever.co/acme", {})
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Backend Engineer"
    assert jobs[0]["location"] == "London"
    assert jobs[0]["url"] == "https://jobs.lever.co/acme/backend"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_lever_board_uses_eu_api_host():
    eu_url = "https://jobs.eu.lever.co/tomtom"
    respx.get(lever_postings_api_url("tomtom", ats_url=eu_url)).mock(
        return_value=Response(
            200,
            json=[
                {
                    "text": "Platform Engineer",
                    "hostedUrl": "https://jobs.eu.lever.co/tomtom/platform",
                    "categories": {"location": "Amsterdam"},
                },
            ],
        ),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_lever_board(client, eu_url, {})
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Platform Engineer"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_lever():
    from relocation_jobs.scrape.board import fetch_ats_board

    respx.get(lever_postings_api_url("acme", ats_url="https://jobs.lever.co/acme")).mock(
        return_value=Response(
            200,
            json=[
                {
                    "text": "Backend Engineer",
                    "hostedUrl": "https://jobs.lever.co/acme/backend",
                    "categories": {"location": "Berlin"},
                },
            ],
        ),
    )
    import httpx

    company = {
        "name": "Acme",
        "ats_type": "lever",
        "ats_url": "https://jobs.lever.co/acme",
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert len(jobs) == 1
    assert jobs[0]["url"].endswith("/backend")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_lever_eu():
    from relocation_jobs.scrape.board import fetch_ats_board

    eu_url = "https://jobs.eu.lever.co/acme"
    respx.get(lever_postings_api_url("acme", ats_url=eu_url)).mock(
        return_value=Response(200, json=[]),
    )
    import httpx

    company = {
        "name": "Acme EU",
        "ats_type": "lever_eu",
        "ats_url": eu_url,
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert jobs == []
