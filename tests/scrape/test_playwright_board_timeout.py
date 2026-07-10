from __future__ import annotations

import time
from unittest.mock import patch

from relocation_jobs.scrape.playwright_board import scrape_board_with_playwright


def test_playwright_board_watchdog_returns_empty_on_timeout(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BOARD_TIMEOUT_SECONDS", "1")

    def _slow_inner(page_url: str) -> list:
        time.sleep(3)
        return [{"title": "job", "url": page_url}]

    with patch(
        "relocation_jobs.scrape.playwright_board._scrape_board_with_playwright_inner",
        side_effect=_slow_inner,
    ):
        started = time.monotonic()
        jobs = scrape_board_with_playwright("https://example.com/careers")
        elapsed = time.monotonic() - started

    assert jobs == []
    assert elapsed < 2.5
