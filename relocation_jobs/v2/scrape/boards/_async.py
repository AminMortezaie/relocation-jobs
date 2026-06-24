from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def run_sync(sync_fn: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.to_thread(sync_fn, *args, **kwargs)


async def fetch_with_playwright_fallback(
    api_fetch: Callable[[], Awaitable[list[dict]]],
    page_url: str,
    *,
    playwright_fallback: Callable[[str], list[dict]] | None = None,
) -> list[dict]:
    from relocation_jobs.v2.scrape.playwright_board import scrape_board_with_playwright

    fallback = playwright_fallback or scrape_board_with_playwright
    try:
        return await api_fetch()
    except Exception:
        return await run_sync(fallback, page_url)
