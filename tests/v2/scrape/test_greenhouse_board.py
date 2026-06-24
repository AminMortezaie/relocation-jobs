from __future__ import annotations

import pytest
import respx
from httpx import Response

from relocation_jobs.v2.scrape.boards.greenhouse import (
    fetch_greenhouse_board,
    greenhouse_jobs_api_url,
)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_greenhouse_board_parses_jobs():
    respx.get(greenhouse_jobs_api_url("acmebackend")).mock(
        return_value=Response(
            200,
            json={
                "jobs": [
                    {
                        "title": "Senior Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acmebackend/jobs/1",
                        "location": {"name": "London"},
                    },
                    {"title": "", "absolute_url": "https://boards.greenhouse.io/acmebackend/jobs/2"},
                ],
            },
        ),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_greenhouse_board(
            client,
            "https://boards.greenhouse.io/acmebackend",
            {},
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Backend Engineer"
    assert jobs[0]["location"] == "London"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_greenhouse():
    from relocation_jobs.v2.scrape.board import fetch_ats_board

    respx.get(greenhouse_jobs_api_url("acmebackend")).mock(
        return_value=Response(
            200,
            json={
                "jobs": [
                    {
                        "title": "Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acmebackend/jobs/9",
                        "location": {"name": "Berlin"},
                    },
                ],
            },
        ),
    )
    import httpx

    company = {
        "name": "Acme Backend Ltd",
        "ats_type": "greenhouse",
        "ats_url": "https://boards.greenhouse.io/acmebackend",
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert len(jobs) == 1
    assert jobs[0]["url"].endswith("/jobs/9")


@pytest.mark.asyncio
async def test_fetch_ats_board_rejects_unknown_type():
    from relocation_jobs.v2.scrape.board import UnsupportedAtsTypeError, fetch_ats_board

    import httpx

    company = {
        "name": "X",
        "ats_type": "unknown_vendor",
        "ats_url": "https://example.personio.de",
    }
    async with httpx.AsyncClient() as client:
        with pytest.raises(UnsupportedAtsTypeError):
            await fetch_ats_board(client, company)
