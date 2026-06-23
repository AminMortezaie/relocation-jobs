"""Merge scraped jobs into cached catalog rows by idempotency key."""

from __future__ import annotations

from datetime import datetime, timezone

from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    stamp_job_identity,
)


def now_iso() -> str:
    """UTC timestamp for fetch ordering (same-day refetches sort correctly)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def merge_matching_jobs(
    existing: list[dict],
    scraped: list[dict],
) -> tuple[list[dict], int, int, int]:
    """
    Merge a fresh scrape into the cached job list keyed by URL idempotency.

    - Same idempotency key: keep original ``fetched`` and ``last_seen``,
      refresh title/visa from scrape when missing.
    - New key: add job with ``fetched`` and ``last_seen`` set to now.
    - Missing from this scrape: keep all cached roles (fetch adds, never removes).

    Returns (merged, preserved_count, new_count, stale_kept_count).
    """
    seen_at = now_iso()
    by_key: dict[str, dict] = {}
    for job in existing:
        key = job_idempotency_key_for_job(job)
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = job
            continue
        # Duplicate rows in cache — keep the one with the earliest fetched date.
        prev_fetched = prev.get("fetched") or "9999-99-99"
        job_fetched = job.get("fetched") or "9999-99-99"
        if job_fetched < prev_fetched:
            by_key[key] = job

    merged: list[dict] = []
    seen: set[str] = set()
    preserved = 0
    new_count = 0

    for job in scraped:
        key = job_idempotency_key(job.get("url", ""))
        if not key or key in seen:
            continue
        seen.add(key)

        if key in by_key:
            old = by_key[key]
            merged_job: dict = {
                "title": job.get("title") or old.get("title", ""),
                "url": old.get("url") or job.get("url", ""),
                "idempotency_key": key,
            }
            # First-seen and last-seen — never bump on re-scrape of same role.
            if old.get("fetched"):
                merged_job["fetched"] = old["fetched"]
            elif job.get("fetched"):
                merged_job["fetched"] = job["fetched"]
            else:
                merged_job["fetched"] = seen_at
            if old.get("last_seen"):
                merged_job["last_seen"] = old["last_seen"]
            elif old.get("fetched"):
                merged_job["last_seen"] = old["fetched"]
            elif job.get("last_seen"):
                merged_job["last_seen"] = job["last_seen"]
            else:
                merged_job["last_seen"] = merged_job["fetched"]

            if old.get("visa_sponsorship") is not None:
                merged_job["visa_sponsorship"] = old["visa_sponsorship"]
            elif job.get("visa_sponsorship") is not None:
                merged_job["visa_sponsorship"] = job["visa_sponsorship"]

            if old.get("applied"):
                merged_job["applied"] = True
                if old.get("applied_date"):
                    merged_job["applied_date"] = old["applied_date"]

            if old.get("not_for_me"):
                merged_job["not_for_me"] = True
                if old.get("not_for_me_date"):
                    merged_job["not_for_me_date"] = old["not_for_me_date"]

            if old.get("rejected"):
                merged_job["rejected"] = True
                if old.get("rejected_date"):
                    merged_job["rejected_date"] = old["rejected_date"]

            _copy_listing_location_fields(merged_job, job, old)

            merged.append(merged_job)
            preserved += 1
        else:
            merged_job = dict(job)
            merged_job["idempotency_key"] = key
            merged_job["fetched"] = merged_job.get("fetched") or seen_at
            merged_job["last_seen"] = seen_at
            merged.append(merged_job)
            new_count += 1

    stale_kept = 0
    for key, old in by_key.items():
        if key not in seen:
            kept = dict(old)
            stamp_job_identity(kept)
            merged.append(kept)
            stale_kept += 1

    for job in merged:
        stamp_job_identity(job)

    return merged, preserved, new_count, stale_kept


def _copy_listing_location_fields(target: dict, *sources: dict) -> None:
    """Preserve listing location metadata from scrape or cache."""
    location = ""
    locations = None
    for source in sources:
        if not location:
            location = (source.get("location") or "").strip()
        if locations is None and source.get("locations"):
            locations = source.get("locations")
    if location:
        target["location"] = location
    if locations:
        target["locations"] = locations


def backfill_listing_locations(jobs: list[dict], scrape_sources: list[dict]) -> None:
    """Copy listing location from the latest scrape onto cached roles.

    Roles kept from cache (including those filtered out by the location gate) still
    receive ``location`` / ``locations`` when the ATS board lists them.
    """
    by_key: dict[str, dict] = {}
    for source in scrape_sources:
        key = job_idempotency_key(source.get("url", ""))
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = source
            continue
        if (source.get("location") or source.get("locations")) and not (
            prev.get("location") or prev.get("locations")
        ):
            by_key[key] = source

    for job in jobs:
        source = by_key.get(job_idempotency_key_for_job(job))
        if source:
            _copy_listing_location_fields(job, source)
