"""Playwright runtime bindings (single patch target for tests)."""

from __future__ import annotations

from relocation_jobs.core.ats_detection import (
    PLAYWRIGHT_AVAILABLE,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # type: ignore[misc, assignment]

__all__ = [
    "PLAYWRIGHT_AVAILABLE",
    "_playwright_browser_context",
    "_playwright_pause",
    "_playwright_sem",
    "sync_playwright",
]
