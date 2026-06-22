"""Stable job identity from careers URLs (idempotency for scrape merges)."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlparse, urlencode, urlunparse

# Query params that identify a specific job posting (ignore tracking noise).
_ID_QUERY_KEYS = frozenset({
    "jobid",
    "job_id",
    "id",
    "gh_jid",
    "gh_src",
    "lever_id",
    "offerapiid",
    "posting",
    "posting_id",
    "position",
    "position_id",
    "req",
    "requisition",
    "requisition_id",
    "vacancy",
    "vacancy_id",
})

_HASH_KEY_RE = re.compile(r"^[a-f0-9]{64}$")
_IDENTITY_HASH_PREFIX = "job:v1:"


def _identity_query(parsed) -> str:
    kept = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key.lower() in _ID_QUERY_KEYS and value:
            kept.append((key.lower(), value))
    kept.sort()
    return urlencode(kept)


def normalize_job_url(url: str) -> str:
    """
    Canonical URL for matching the same job across scrapes.

    Lowercases host, strips www, keeps job-id query params, drops fragment,
    trims trailing slash.
    """
    raw = (url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    path = parsed.path or ""
    if path != "/":
        path = path.rstrip("/")
    if not path:
        path = "/"

    query = _identity_query(parsed)
    return urlunparse((scheme, host, path, "", query, ""))


def job_idempotency_key(url: str) -> str:
    """SHA-256 hex digest of the normalized URL (fixed 64-char key)."""
    canonical = normalize_job_url(url)
    if not canonical:
        return ""
    payload = f"{_IDENTITY_HASH_PREFIX}{canonical}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_idempotency_hash(key: str) -> bool:
    return bool(_HASH_KEY_RE.fullmatch((key or "").strip().lower()))


def job_idempotency_key_for_job(job: dict) -> str:
    """Return idempotency key for a job, always derived from its URL."""
    return job_idempotency_key(job.get("url", ""))


def stamp_job_identity(job: dict) -> dict:
    """Ensure job dict carries idempotency_key hash; return the same dict."""
    key = job_idempotency_key(job.get("url", ""))
    if key:
        job["idempotency_key"] = key
    return job


def backfill_job_identities(data: dict, *, force: bool = False) -> int:
    """Stamp idempotency_key on all matching_jobs; return number of jobs updated."""
    updated = 0
    for company in data.get("companies") or []:
        for job in company.get("matching_jobs") or []:
            before = job.get("idempotency_key")
            if not force and is_idempotency_hash(before or ""):
                continue
            stamp_job_identity(job)
            if job.get("idempotency_key") and job.get("idempotency_key") != before:
                updated += 1
    return updated
