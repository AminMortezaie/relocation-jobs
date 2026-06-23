"""Playwright and static-HTML generic career page scrapers."""

from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import jobs_from_listing_html, jobs_from_listing_html_async
from relocation_jobs.scrape.playwright import (
    PLAYWRIGHT_AVAILABLE,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
    sync_playwright,
)


def scrape_generic(url: str) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    Fetch error: {e}")
        return []

    return jobs_from_listing_html(r.text, url)


def scrape_with_playwright(
    page_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    """Render JS-heavy pages with Playwright and extract job links from DOM."""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as p:
                browser, context = _playwright_browser_context(p)
                page = context.new_page()
                page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
                _playwright_pause(page, 3500)
                raise_if_cancelled()
                html = page.content()
                browser.close()

        return jobs_from_listing_html(html, page_url, relevant_only=relevant_only)
    except FetchCancelled:
        raise
    except Exception as e:
        print(f"    Playwright error ({page_url}): {e}")
        return []


async def scrape_generic_async(
    client: httpx.AsyncClient,
    url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    try:
        r = await client.get(url, timeout=15.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Fetch error: {e}")
        return []
    return await jobs_from_listing_html_async(
        r.text, url, client, relevant_only=relevant_only
    )
