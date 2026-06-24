from __future__ import annotations

from collections.abc import Callable

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.core.scrape_cancel import raise_if_cancelled
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.dom_listing import jobs_from_listing_html
from relocation_jobs.scrape.playwright_board import scrape_board_with_playwright

PlaywrightFallback = Callable[[str], list[dict]]


async def _fetch_generic_http(client, page_url: str) -> list[dict]:
    try:
        response = await client.get(page_url, headers=HEADERS, timeout=15.0)
        response.raise_for_status()
    except Exception:
        return []
    return await run_sync(jobs_from_listing_html, response.text, page_url, relevant_only=False)


async def fetch_generic_board(
    client,
    board_url: str,
    company: dict,
    *,
    playwright_fallback: PlaywrightFallback | None = None,
) -> list[dict]:
    page_url = (company.get("careers_url") or board_url or "").strip()
    if not page_url:
        return []

    fallback = playwright_fallback or scrape_board_with_playwright
    jobs = await _fetch_generic_http(client, page_url)
    if jobs:
        return jobs
    raise_if_cancelled()
    return await run_sync(fallback, page_url)
