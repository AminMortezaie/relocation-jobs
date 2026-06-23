"""Shared HTTP clients for scraper modules (single patch target for tests)."""

from __future__ import annotations

import requests

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE

if HTTPX_AVAILABLE:
    import httpx

__all__ = ["httpx", "requests"]
