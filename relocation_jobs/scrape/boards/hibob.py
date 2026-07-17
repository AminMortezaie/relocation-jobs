from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Optional
from urllib.parse import urlparse

from relocation_jobs.core.ats_detection import (
    PLAYWRIGHT_AVAILABLE,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
)
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled

if PLAYWRIGHT_AVAILABLE:
    from playwright.sync_api import sync_playwright
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.descriptions import html_to_readable
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.playwright_board import scrape_board_with_playwright

PlaywrightFallback = Callable[[str], list[dict]]
HibobPayloadFetcher = Callable[[str], Optional[dict[str, Any]]]

_HIBOB_HOST_RE = re.compile(r"([a-z0-9-]+)\.careers\.hibob\.com", re.I)
_HIBOB_JOB_URL_RE = re.compile(
    r"careers\.hibob\.com/jobs/([0-9a-f-]{36})",
    re.I,
)
_HIBOB_JOB_AD_API = re.compile(r"/api/job-ad(?:\?|$)")


def hibob_board_slug(board_url: str) -> str:
    match = _HIBOB_HOST_RE.search(board_url or "")
    return match.group(1) if match else ""


def hibob_board_url(slug: str) -> str:
    return f"https://{slug}.careers.hibob.com/jobs"


def hibob_job_url(slug: str, job_id: str) -> str:
    return f"{hibob_board_url(slug).rstrip('/')}/{job_id}"


def hibob_job_id_from_url(url: str) -> str:
    match = _HIBOB_JOB_URL_RE.search(url or "")
    return match.group(1) if match else ""


def hibob_listing_page_url(board_url: str, company: dict) -> str:
    page_url = (board_url or company.get("careers_url") or "").strip()
    if not page_url:
        return ""
    parsed = urlparse(page_url)
    if not parsed.scheme or not parsed.netloc:
        return page_url
    path = parsed.path.rstrip("/") or "/jobs"
    if path == "":
        path = "/jobs"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def hibob_location(row: dict) -> str | None:
    site = (row.get("site") or "").strip()
    country = (row.get("country") or "").strip()
    parts = [part for part in (site, country) if part]
    return ", ".join(dict.fromkeys(parts)) or None


def hibob_description_html(row: dict) -> str:
    parts = [
        (row.get("description") or "").strip(),
        (row.get("requirements") or "").strip(),
        (row.get("responsibilities") or "").strip(),
        (row.get("benefits") or "").strip(),
    ]
    return "\n\n".join(part for part in parts if part)


def parse_hibob_jobs(payload: dict[str, Any], slug: str) -> list[dict]:
    jobs: list[dict] = []
    for row in payload.get("jobAdDetails") or []:
        title = (row.get("title") or "").strip()
        job_id = (row.get("id") or "").strip()
        if not title or not job_id:
            continue
        job = listing_job(
            title,
            hibob_job_url(slug, job_id),
            location=hibob_location(row),
        )
        description = hibob_description_html(row)
        if description:
            job["description_text"] = html_to_readable(description)
        jobs.append(job)
    return jobs


def fetch_hibob_job_ads_sync(page_url: str) -> dict[str, Any] | None:
    if not PLAYWRIGHT_AVAILABLE:
        return None
    captured: dict[str, Any] | None = None

    def on_response(response) -> None:
        nonlocal captured
        if captured is not None:
            return
        if response.request.resource_type not in ("xhr", "fetch"):
            return
        if not _HIBOB_JOB_AD_API.search(response.url):
            return
        try:
            payload = response.json()
        except Exception:
            return
        if isinstance(payload, dict) and isinstance(payload.get("jobAdDetails"), list):
            captured = payload

    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as playwright:
                browser, context = _playwright_browser_context(playwright)
                page = context.new_page()
                page.on("response", on_response)
                page.goto(page_url, wait_until="networkidle", timeout=60000)
                _playwright_pause(page, 2000)
                raise_if_cancelled()
                browser.close()
    except FetchCancelled:
        raise
    except Exception:
        return None
    return captured


def fetch_hibob_job_detail(url: str) -> tuple[str, str]:
    job_id = hibob_job_id_from_url(url)
    slug = hibob_board_slug(url)
    if not job_id or not slug:
        return "", ""
    payload = fetch_hibob_job_ads_sync(hibob_board_url(slug))
    if not payload:
        return "", ""
    for row in payload.get("jobAdDetails") or []:
        if (row.get("id") or "").strip() == job_id:
            description = hibob_description_html(row)
            text = html_to_readable(description) if description else ""
            location = (hibob_location(row) or "").strip()
            return text, location
    return "", ""


def fetch_hibob_job_text(url: str) -> str:
    text, _location = fetch_hibob_job_detail(url)
    return text


async def fetch_hibob_board(
    client,
    board_url: str,
    company: dict,
    *,
    payload_fetcher: HibobPayloadFetcher | None = None,
    playwright_fallback: PlaywrightFallback | None = None,
) -> list[dict]:
    del client
    page_url = hibob_listing_page_url(board_url, company)
    slug = hibob_board_slug(page_url)
    if not slug:
        return []

    fetch_payload = payload_fetcher or fetch_hibob_job_ads_sync
    payload = await run_sync(fetch_payload, page_url)
    if payload:
        jobs = parse_hibob_jobs(payload, slug)
        if jobs:
            return jobs

    fallback = playwright_fallback or scrape_board_with_playwright
    return await run_sync(fallback, page_url)
