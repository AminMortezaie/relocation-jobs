"""Job tracking business logic.

Coordinates the catalog (get_job_by_url, get_company) with the job repository (db/tracking.py).
No raw SQL here — all DB access goes through catalog_db or db/.
Service layer: uses Pydantic schemas for response validation.
All public functions return dicts complying with JobStatusUpdate schema.
See SCHEMAS.md for full schema definitions.
"""

from __future__ import annotations

from urllib.parse import urlparse

from relocation_jobs.catalog_db import get_company, get_job_by_url
from relocation_jobs.db import (
    load_wrong_location_hides_db,
    reapply_job_db,
    set_company_awaiting_response_db,
    set_job_applied_db,
    set_job_ats_score_db,
    set_job_looking_to_apply_db,
    set_job_not_for_me_db,
    set_job_rejected_db,
    set_job_seen_db,
    set_job_waiting_referral_db,
    sync_company_applied_from_jobs_db,
)
from relocation_jobs.core.location_tags import (
    city_match_keys,
    company_expected_locations,
    job_matches_expected_locations,
)
from relocation_jobs.schemas import JobStatusUpdate
from relocation_jobs.services.company_service import find_job_in_data


def _normalize_linkedin_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    host = (urlparse(raw).netloc or "").lower()
    if "linkedin.com" not in host:
        raise ValueError("Enter a LinkedIn profile URL (linkedin.com/in/…)")
    return raw


def _normalize_linkedin(url: str) -> str:
    return _normalize_linkedin_url(url)


def set_job_applied(
    country_key: str,
    company_name: str,
    job_url: str,
    applied: bool,
    *,
    user_id: int,
) -> dict:
    """Mark/unmark job as applied.

    Returns dict complying with JobStatusUpdate schema.
    """
    job = get_job_by_url(job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    result = set_job_applied_db(
        user_id, country_key, company_name, job_url, applied,
        job_title=job.get("title", ""),
    )
    sync_company_applied_from_jobs_db(user_id, country_key, company_name)
    if applied:
        set_company_awaiting_response_db(user_id, country_key, company_name, True, preserve_date=True)
    JobStatusUpdate(**result)
    return result


def set_job_rejected(
    country_key: str,
    company_name: str,
    job_url: str,
    rejected: bool,
    *,
    user_id: int,
) -> dict:
    """Mark/unmark job as rejected.

    Returns dict complying with JobStatusUpdate schema.
    """
    job = get_job_by_url(job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    result = set_job_rejected_db(
        user_id, country_key, company_name, job_url, rejected,
        job_title=job.get("title", ""),
    )
    JobStatusUpdate(**result)
    return result


def set_job_reapply(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
) -> dict:
    """Reapply to a previously rejected job.

    Returns dict complying with JobStatusUpdate schema.
    """
    job = get_job_by_url(job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    result = reapply_job_db(user_id, country_key, company_name, job_url)
    JobStatusUpdate(**result)
    return result


def set_job_waiting_referral(
    country_key: str,
    company_name: str,
    job_url: str,
    waiting_referral: bool,
    *,
    user_id: int,
    linkedin_url: str = "",
) -> dict:
    """Mark/unmark job as waiting for referral with LinkedIn URL.

    Returns dict complying with JobStatusUpdate schema.
    """
    job = get_job_by_url(job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    normalized_linkedin = _normalize_linkedin(linkedin_url) if waiting_referral else ""
    result = set_job_waiting_referral_db(
        user_id, country_key, company_name, job_url, waiting_referral,
        linkedin_url=normalized_linkedin,
        job_title=job.get("title", ""),
    )
    JobStatusUpdate(**result)
    return result


def set_job_ats_score(
    country_key: str,
    company_name: str,
    job_url: str,
    ats_score: int | None,
    *,
    user_id: int,
) -> dict:
    """Set ATS score for job (0-100 or None to clear).

    Returns dict complying with JobStatusUpdate schema.
    """
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    job = get_job_by_url(job_url)
    result = set_job_ats_score_db(
        user_id, country_key, company_name, job_url, ats_score,
        job_title=job.get("title", "") if job else "",
    )
    JobStatusUpdate(**result)
    return result


def set_job_looking_to_apply(
    country_key: str,
    company_name: str,
    job_url: str,
    looking_to_apply: bool,
    *,
    user_id: int,
) -> dict:
    """Mark/unmark job as looking-to-apply.

    Returns dict complying with JobStatusUpdate schema.
    """
    job = get_job_by_url(job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    result = set_job_looking_to_apply_db(
        user_id, country_key, company_name, job_url, looking_to_apply,
        job_title=job.get("title", ""),
    )
    JobStatusUpdate(**result)
    return result


def set_job_seen(
    country_key: str,
    company_name: str,
    job_url: str,
    seen: bool = True,
    *,
    user_id: int,
) -> dict:
    """Mark/unmark job as seen.

    Returns dict complying with JobStatusUpdate schema.
    """
    job = get_job_by_url(job_url)
    result = set_job_seen_db(
        user_id, country_key, company_name, job_url, seen,
        job_title=job.get("title", "") if job else "",
    )
    JobStatusUpdate(**result)
    return result


def set_job_not_for_me(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
    not_for_me: bool = True,
    reason: str | None = None,
) -> dict:
    """Mark/unmark job as not-for-me with optional reason.

    Returns dict complying with JobStatusUpdate schema.
    """
    job = get_job_by_url(job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    result = set_job_not_for_me_db(
        user_id, country_key, company_name, job_url,
        not_for_me=not_for_me, reason=reason,
    )
    JobStatusUpdate(**result)
    return result


def reconcile_wrong_location_hides(
    user_id: int,
    *,
    country_key: str | None = None,
    city_label: str | None = None,
) -> int:
    rows = load_wrong_location_hides_db(user_id, country_key)
    target_city_keys = city_match_keys(city_label) if city_label else set()
    restored = 0

    for row in rows:
        country = row["country"]
        company_name = row["company_name"]
        job_url = row["job_url"]

        company = get_company(country, company_name)
        if company is None:
            continue
        job = find_job_in_data({"companies": [company]}, company_name, job_url)
        if job is None:
            continue

        expected = company_expected_locations(company, catalog_country=country)
        if target_city_keys:
            office_keys = {key for loc in expected for key in city_match_keys(loc["city"])}
            if not (office_keys & target_city_keys):
                continue

        ok, _ = job_matches_expected_locations(job, expected)
        if not ok:
            continue

        set_job_not_for_me_db(user_id, country, company_name, job_url, not_for_me=False)
        restored += 1

    return restored
