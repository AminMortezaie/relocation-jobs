"""Panel subprocess IPC: progress, review, and activity reporting."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable

from relocation_jobs.core.job_identity import job_idempotency_key
from relocation_jobs.core.location_tags import (
    company_expected_locations,
    job_matches_expected_locations,
)
from relocation_jobs.scrape.listing import is_listing_noise_url
from relocation_jobs.scrape.relevance import explain_title_filter, is_relevant

_progress_reporter: Callable[[dict], None] | None = None
_review_reporter: Callable[[dict], None] | None = None


def emit_panel_ipc(kind: str, payload: dict) -> None:
    """Stdout markers consumed by panel_server when scraping in a subprocess."""
    if os.environ.get("PANEL_SCRAPE_CHILD"):
        print(f"@@{kind}@@{json.dumps(payload, separators=(',', ':'))}", flush=True)


def report_activity(message: str, *, detail: str = "") -> None:
    message = (message or "").strip()
    if not message:
        return
    emit_panel_ipc("ACTIVITY", {"message": message, "detail": (detail or "").strip()})


def set_progress_reporter(reporter: Callable[[dict], None] | None) -> None:
    global _progress_reporter
    _progress_reporter = reporter


def clear_progress_reporter() -> None:
    set_progress_reporter(None)


def set_review_reporter(reporter: Callable[[dict], None] | None) -> None:
    global _review_reporter
    _review_reporter = reporter


def clear_review_reporter() -> None:
    set_review_reporter(None)


def report_progress(
    *,
    current: int,
    total: int,
    company: str | None = None,
    status: str = "",
    new_jobs: int | None = None,
) -> None:
    payload = {
        "current": current,
        "total": total,
        "company": company,
        "status": status,
    }
    if new_jobs is not None:
        payload["new_jobs"] = int(new_jobs)
    if _progress_reporter:
        _progress_reporter(payload)
    emit_panel_ipc("PROGRESS", payload)


_JUNK_REVIEW_TITLE = re.compile(
    r"^(show\s+\d+\s+more|load\s+more|view\s+all(\s+jobs)?|see\s+all(\s+jobs)?)$",
    re.I,
)


def review_entry(j: dict) -> dict | None:
    url = (j.get("url") or "").strip()
    if not url or is_listing_noise_url(url):
        return None
    title = (j.get("title") or "").strip()
    if title and _JUNK_REVIEW_TITLE.match(title):
        return None
    entry = {"title": title or url, "url": url}
    reason = (j.get("filter_reason") or j.get("location_filter_reason") or "").strip()
    if reason:
        entry["filter_reason"] = reason
    return entry


def review_filtered_jobs(
    all_scraped: list[dict],
    scraped: list[dict],
    company: dict,
    *,
    catalog_country: str = "",
) -> list[dict]:
    """Jobs seen on the board that did not match title/location filters, with reasons."""
    included_keys = {
        job_idempotency_key(j.get("url", ""))
        for j in scraped
    }
    expected = company_expected_locations(company, catalog_country=catalog_country)
    filtered: list[dict] = []
    seen: set[str] = set()
    for job in all_scraped:
        url = (job.get("url") or "").strip()
        if not url:
            continue
        key = job_idempotency_key(url)
        if key in included_keys or key in seen:
            continue
        title = (job.get("title") or "").strip()
        if not is_relevant(title):
            reason = explain_title_filter(title)
        elif expected:
            ok, loc_reason = job_matches_expected_locations(job, expected)
            reason = loc_reason or "location mismatch" if not ok else ""
        else:
            reason = "not matched"
        if not reason:
            continue
        filtered.append({**job, "filter_reason": reason})
        seen.add(key)
    return filtered


def report_review_jobs(
    *,
    included: list[dict],
    filtered: list[dict],
) -> None:
    payload = {
        "included": [e for j in included if (e := review_entry(j))],
        "filtered": [e for j in filtered if (e := review_entry(j))],
    }
    if _review_reporter:
        _review_reporter(payload)
    emit_panel_ipc("REVIEW", payload)
