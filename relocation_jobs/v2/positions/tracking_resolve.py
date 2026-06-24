from __future__ import annotations

from relocation_jobs.core.db import _normalize_url
from relocation_jobs.core.job_identity import job_idempotency_key


def resolve_tracking_url(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> str:
    """Return the tracking row URL for this job (exact or idempotency alias)."""
    job_url = _normalize_url(job_url)
    job_key = job_idempotency_key(job_url)
    if not job_key:
        return job_url
    rows = conn.execute(
        """
        SELECT job_url FROM job_tracking
        WHERE user_id = %s AND country = %s AND company_name = %s
        """,
        (user_id, country, company_name),
    ).fetchall()
    alias = job_url
    for row in rows:
        stored = _normalize_url(row.get("job_url", ""))
        if stored == job_url:
            return job_url
        if job_idempotency_key(stored) == job_key:
            alias = stored
    return alias


def tracking_urls_for_job(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> set[str]:
    """All tracking URLs that refer to the same job (normalized + idempotency aliases)."""
    canonical_url = _normalize_url(job_url)
    urls = {canonical_url}
    job_key = job_idempotency_key(canonical_url)
    if not job_key:
        return urls
    rows = conn.execute(
        """
        SELECT job_url FROM job_tracking
        WHERE user_id = %s AND country = %s AND company_name = %s
        """,
        (user_id, country, company_name),
    ).fetchall()
    for row in rows:
        stored = _normalize_url(row.get("job_url", ""))
        if job_idempotency_key(stored) == job_key:
            urls.add(stored)
    return urls
