from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from playwright.sync_api import sync_playwright

from relocation_jobs.core.ats_detection import (
    PLAYWRIGHT_AVAILABLE,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
)
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.fetch.timeouts import playwright_board_timeout_seconds
from relocation_jobs.scrape.dom_listing import jobs_from_listing_html

LOGGER = logging.getLogger(__name__)


def _scrape_board_with_playwright_inner(page_url: str) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        return []
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


def scrape_board_with_playwright(page_url: str) -> list[dict]:
    timeout = playwright_board_timeout_seconds()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_scrape_board_with_playwright_inner, page_url)
        return future.result(timeout=timeout)
    except FetchCancelled:
        raise
    except FuturesTimeoutError:
        LOGGER.warning(
            "Playwright board scrape timed out after %ss: %s",
            timeout,
            page_url,
        )
        return []
    except Exception:
        return []
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
