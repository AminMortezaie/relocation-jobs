from __future__ import annotations

from playwright.sync_api import sync_playwright

from relocation_jobs.core.ats_detection import (
    PLAYWRIGHT_AVAILABLE,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
)
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.v2.scrape.dom_listing import jobs_from_listing_html


def scrape_board_with_playwright(page_url: str) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        return []
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as playwright:
                browser, context = _playwright_browser_context(playwright)
                page = context.new_page()
                page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
                _playwright_pause(page, 3500)
                raise_if_cancelled()
                html = page.content()
                browser.close()
        return jobs_from_listing_html(html, page_url, relevant_only=False)
    except FetchCancelled:
        raise
    except Exception:
        return []
