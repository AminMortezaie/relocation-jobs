from __future__ import annotations

import asyncio
from collections.abc import Callable

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.v2.scrape.listing import listing_job
from relocation_jobs.v2.scrape.playwright_board import scrape_board_with_playwright

PlaywrightFallback = Callable[[str], list[dict]]


def ashby_board_slug(ats_url: str) -> str:
    return ats_url.rstrip("/").split("/")[-1].split("?")[0]


def ashby_job_board_api_url(slug: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"


def parse_ashby_api_jobs(payload: dict, ats_url: str) -> list[dict]:
    jobs: list[dict] = []
    for row in payload.get("jobs") or []:
        title = (row.get("title") or "").strip()
        url = (row.get("jobUrl") or ats_url).strip()
        if not title or not url:
            continue
        location = row.get("location") or row.get("locationName")
        jobs.append(listing_job(title, url, location=location))
    return jobs


async def _fetch_ashby_api(client, ats_url: str) -> list[dict]:
    slug = ashby_board_slug(ats_url)
    if not slug:
        return []
    response = await client.get(
        ashby_job_board_api_url(slug),
        headers=HEADERS,
        timeout=10.0,
    )
    response.raise_for_status()
    return parse_ashby_api_jobs(response.json(), ats_url)


async def fetch_ashby_board(
    client,
    board_url: str,
    company: dict,
    *,
    playwright_fallback: PlaywrightFallback | None = None,
) -> list[dict]:
    fallback = playwright_fallback or scrape_board_with_playwright
    try:
        return await _fetch_ashby_api(client, board_url)
    except Exception:
        careers_url = (company.get("careers_url") or board_url).strip()
        return await asyncio.to_thread(fallback, careers_url)
