from __future__ import annotations

from relocation_jobs.core.ats_detection import (
    PLAYWRIGHT_AVAILABLE,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
)

if PLAYWRIGHT_AVAILABLE:
    from playwright.sync_api import sync_playwright
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.listing import listing_job


def scrape_jibe_board_sync(careers_url: str) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        return []
    merged: dict[str, str] = {}
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as playwright:
                browser, context = _playwright_browser_context(playwright)
                page = context.new_page()
                page.goto(careers_url, wait_until="networkidle", timeout=90000)
                _playwright_pause(page, 5000)
                for _ in range(20):
                    raise_if_cancelled()
                    batch = page.evaluate(
                        """() => {
                          const out = [];
                          for (const a of document.querySelectorAll("a[href*='/jobs/']")) {
                            const h = a.href.split('?')[0];
                            const t = a.innerText.trim();
                            if (h.includes('login') || t.length < 5) continue;
                            if (!out.find(x => x.h === h)) out.push({h, t});
                          }
                          return out;
                        }"""
                    )
                    for row in batch:
                        merged[row["h"]] = row["t"]
                    next_btn = page.query_selector(
                        "button[aria-label='Next Page of Job Search Results']"
                    )
                    if not next_btn or next_btn.get_attribute("disabled"):
                        break
                    next_btn.click()
                    _playwright_pause(page, 4000)
                browser.close()
    except FetchCancelled:
        raise
    except Exception:
        return []
    return [listing_job(title, url) for url, title in merged.items()]


def scrape_atlassian_board_sync(careers_url: str) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        return []
    merged: dict[str, str] = {}
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as playwright:
                browser, context = _playwright_browser_context(playwright)
                page = context.new_page()
                page.goto(careers_url, wait_until="networkidle", timeout=90000)
                _playwright_pause(page, 8000)
                raise_if_cancelled()
                batch = page.evaluate(
                    """() => {
                      const out = [];
                      for (const a of document.querySelectorAll("a[href*='/careers/details/']")) {
                        const h = a.href.split('?')[0];
                        const t = a.innerText.trim();
                        if (t.length < 5) continue;
                        if (!out.find(x => x.h === h)) out.push({h, t});
                      }
                      return out;
                    }"""
                )
                for row in batch:
                    merged[row["h"]] = row["t"]
                browser.close()
    except FetchCancelled:
        raise
    except Exception:
        return []
    return [listing_job(title, url) for url, title in merged.items()]


async def fetch_jibe_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("careers_url") or "")
    return await run_sync(scrape_jibe_board_sync, url)


async def fetch_atlassian_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("careers_url") or "")
    return await run_sync(scrape_atlassian_board_sync, url)
