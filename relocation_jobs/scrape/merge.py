from __future__ import annotations

from datetime import datetime, timezone

from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    stamp_job_identity,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy_location_fields(target: dict, *sources: dict) -> None:
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


def _index_existing_by_key(existing: list[dict]) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    for job in existing:
        key = job_idempotency_key_for_job(job)
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None or (job.get("fetched") or "9999") < (prev.get("fetched") or "9999"):
            by_key[key] = job
    return by_key


def _update_from_scrape(old: dict, scraped: dict, key: str, seen_at: str) -> dict:
    out: dict = {
        "title": scraped.get("title") or old.get("title", ""),
        "url": old.get("url") or scraped.get("url", ""),
        "idempotency_key": key,
        "fetched": old.get("fetched") or scraped.get("fetched") or seen_at,
        "last_seen": seen_at,
    }
    if old.get("visa_sponsorship") is not None:
        out["visa_sponsorship"] = old["visa_sponsorship"]
    elif scraped.get("visa_sponsorship") is not None:
        out["visa_sponsorship"] = scraped["visa_sponsorship"]
    _copy_location_fields(out, scraped, old)
    return out


def _add_from_scrape(scraped: dict, key: str, seen_at: str) -> dict:
    out = dict(scraped)
    out["idempotency_key"] = key
    out["fetched"] = out.get("fetched") or seen_at
    out["last_seen"] = seen_at
    return out


def merge_matching_jobs(
    existing: list[dict],
    scraped: list[dict],
) -> tuple[list[dict], int, int, int]:
    seen_at = now_iso()
    cache = _index_existing_by_key(existing)

    merged: list[dict] = []
    scraped_keys: set[str] = set()
    preserved = 0
    new_count = 0

    for job in scraped:
        key = job_idempotency_key(job.get("url", ""))
        if not key or key in scraped_keys:
            continue
        scraped_keys.add(key)

        old = cache.get(key)
        if old is not None:
            merged.append(_update_from_scrape(old, job, key, seen_at))
            preserved += 1
        else:
            merged.append(_add_from_scrape(job, key, seen_at))
            new_count += 1

    stale_kept = 0
    for key, old in cache.items():
        if key in scraped_keys:
            continue
        kept = dict(old)
        stamp_job_identity(kept)
        merged.append(kept)
        stale_kept += 1

    for job in merged:
        stamp_job_identity(job)

    return merged, preserved, new_count, stale_kept
