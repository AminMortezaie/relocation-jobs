"""Single-company fetch review: included vs filtered roles with reasons."""

from __future__ import annotations

import re

from relocation_jobs.core.job_identity import job_idempotency_key
from relocation_jobs.core.location_tags import (
    company_expected_locations,
    job_matches_expected_locations,
)
from relocation_jobs.scrape.dom_listing import _is_listing_noise_url
from relocation_jobs.scrape.relevance import explain_title_filter, is_relevant

_JUNK_REVIEW_TITLE = re.compile(
    r"^(show\s+\d+\s+more|load\s+more|view\s+all(\s+jobs)?|see\s+all(\s+jobs)?)$",
    re.I,
)


def review_entry(job: dict) -> dict | None:
    url = (job.get("url") or "").strip()
    if not url or _is_listing_noise_url(url):
        return None
    title = (job.get("title") or "").strip()
    if title and _JUNK_REVIEW_TITLE.match(title):
        return None
    entry = {"title": title or url, "url": url}
    reason = (job.get("filter_reason") or job.get("location_filter_reason") or "").strip()
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


def build_review_payload(
    *,
    included: list[dict],
    filtered: list[dict],
) -> dict:
    return {
        "included": [e for j in included if (e := review_entry(j))],
        "filtered": [e for j in filtered if (e := review_entry(j))],
    }
