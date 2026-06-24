from __future__ import annotations

import pytest
import respx
from httpx import Response

from relocation_jobs.scrape.boards.generic import fetch_generic_board

_LISTING_HTML = """
<html><body>
  <a href="/jobs/backend-engineer">Backend Engineer</a>
  <a href="/jobs/data-scientist">Data Scientist</a>
</body></html>
"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_generic_board_parses_listing_html():
    respx.get("https://careers.example.com/").mock(
        return_value=Response(200, text=_LISTING_HTML),
    )
    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_generic_board(
            client,
            "https://careers.example.com/",
            {"careers_url": "https://careers.example.com/"},
        )
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Backend Engineer"
    assert jobs[0]["url"] == "https://careers.example.com/jobs/backend-engineer"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_generic_board_playwright_fallback():
    respx.get("https://careers.example.com/").mock(
        return_value=Response(500, text="error"),
    )
    import httpx

    def fake_playwright(url: str) -> list[dict]:
        assert url == "https://careers.example.com/"
        return [{"title": "Platform Engineer", "url": "https://careers.example.com/jobs/platform"}]

    async with httpx.AsyncClient() as client:
        jobs = await fetch_generic_board(
            client,
            "https://careers.example.com/",
            {"careers_url": "https://careers.example.com/"},
            playwright_fallback=fake_playwright,
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Platform Engineer"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ats_board_dispatches_generic():
    from relocation_jobs.scrape.board import fetch_ats_board

    respx.get("https://careers.example.com/").mock(
        return_value=Response(200, text=_LISTING_HTML),
    )
    import httpx

    company = {
        "name": "Acme",
        "ats_type": "generic",
        "careers_url": "https://careers.example.com/",
    }
    async with httpx.AsyncClient() as client:
        jobs = await fetch_ats_board(client, company)
    assert len(jobs) == 2
    assert jobs[0]["url"].endswith("/jobs/backend-engineer")
