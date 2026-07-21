from __future__ import annotations

import pytest
import respx
from httpx import Response

from relocation_jobs.scrape.boards.remoteok import (
    fetch_remoteok_board,
    parse_remoteok_api_payload,
    remoteok_api_url,
)


def test_remoteok_api_url_defaults_and_preserves_tags():
    assert remoteok_api_url("") == "https://remoteok.com/api?tags=dev"
    assert remoteok_api_url("https://remoteok.com/api?tags=software").endswith("tags=software")
    assert remoteok_api_url("https://remoteok.com/") == "https://remoteok.com/api"


def test_parse_remoteok_api_payload_skips_legal_and_maps_employer():
    payload = [
        {"legal": "credit Remote OK", "last_updated": 1},
        {
            "id": 1,
            "position": "Senior Backend Engineer",
            "company": "Acme",
            "url": "https://remoteOK.com/remote-jobs/acme-backend-1",
            "location": "Worldwide",
            "tags": ["dev", "backend"],
            "description": "<p>Build APIs</p>",
        },
        {
            "id": 2,
            "position": "Sales Director",
            "company": "SalesCo",
            "url": "https://remoteOK.com/remote-jobs/sales-2",
            "tags": ["sales"],
            "description": "Sell things",
        },
    ]
    jobs = parse_remoteok_api_payload(payload, board_url="https://remoteok.com/api?tags=dev")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Backend Engineer"
    assert jobs[0]["employer"] == "Acme"
    assert jobs[0]["url"].endswith("acme-backend-1")
    assert "Build APIs" in jobs[0]["description_text"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_remoteok_board_and_dispatch():
    respx.get("https://remoteok.com/api?tags=dev").mock(
        return_value=Response(
            200,
            json=[
                {"legal": "ok"},
                {
                    "position": "Platform Engineer",
                    "company": "Orbit",
                    "url": "https://remoteOK.com/remote-jobs/orbit-platform-9",
                    "tags": ["dev", "platform"],
                    "description": "Ship platform work",
                },
            ],
        ),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_remoteok_board(
            client,
            "https://remoteok.com/api?tags=dev",
            {"name": "Remote OK"},
        )
    assert len(jobs) == 1
    assert jobs[0]["employer"] == "Orbit"

    from relocation_jobs.scrape.board import fetch_ats_board

    company = {
        "name": "Remote OK",
        "ats_type": "remoteok",
        "ats_url": "https://remoteok.com/api?tags=dev",
        "careers_url": "https://remoteok.com/api?tags=dev",
    }
    async with httpx.AsyncClient() as client:
        dispatched = await fetch_ats_board(client, company)
    assert len(dispatched) == 1
