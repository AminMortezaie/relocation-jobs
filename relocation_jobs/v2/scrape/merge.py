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


def merge_matching_jobs(
    existing: list[dict],
    scraped: list[dict],
) -> tuple[list[dict], int, int, int]:
    seen_at = now_iso()
    by_key: dict[str, dict] = {}
    for job in existing:
        key = job_idempotency_key_for_job(job)
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None or (job.get("fetched") or "9999") < (prev.get("fetched") or "9999"):
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
            merged_job["fetched"] = old.get("fetched") or job.get("fetched") or seen_at
            merged_job["last_seen"] = old.get("last_seen") or old.get("fetched") or seen_at
            if old.get("visa_sponsorship") is not None:
                merged_job["visa_sponsorship"] = old["visa_sponsorship"]
            elif job.get("visa_sponsorship") is not None:
                merged_job["visa_sponsorship"] = job["visa_sponsorship"]
            _copy_location_fields(merged_job, job, old)
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
