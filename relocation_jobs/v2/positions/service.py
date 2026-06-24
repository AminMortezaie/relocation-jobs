from __future__ import annotations

from urllib.parse import urlparse

from relocation_jobs.core.location_tags import (
    city_match_keys,
    company_expected_locations,
    job_matches_expected_locations,
)
from relocation_jobs.v2.catalog.lookup import find_job_in_data
from relocation_jobs.v2.catalog.repo import get_company, get_job_by_url
from relocation_jobs.v2.positions import repo
from relocation_jobs.v2.positions.types import JobStatusUpdate


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


def _require_catalog_job(company_name: str, job_url: str) -> dict:
    job = get_job_by_url(job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return job


def _validated(result: dict) -> dict:
    JobStatusUpdate(**result)
    return result


def set_job_applied(
    country_key: str,
    company_name: str,
    job_url: str,
    applied: bool,
    *,
    user_id: int,
) -> dict:
    job = _require_catalog_job(company_name, job_url)
    result = repo.set_applied(
        user_id, country_key, company_name, job_url, applied,
        job_title=job.get("title", ""),
    )
    repo.sync_company_applied(user_id, country_key, company_name)
    if applied:
        repo.set_company_awaiting_response(
            user_id, country_key, company_name, True, preserve_date=True,
        )
    return _validated(result)


def set_job_rejected(
    country_key: str,
    company_name: str,
    job_url: str,
    rejected: bool,
    *,
    user_id: int,
) -> dict:
    job = _require_catalog_job(company_name, job_url)
    result = repo.set_rejected(
        user_id, country_key, company_name, job_url, rejected,
        job_title=job.get("title", ""),
    )
    return _validated(result)


def set_job_reapply(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
) -> dict:
    _require_catalog_job(company_name, job_url)
    return _validated(repo.reapply(user_id, country_key, company_name, job_url))


def set_job_waiting_referral(
    country_key: str,
    company_name: str,
    job_url: str,
    waiting_referral: bool,
    *,
    user_id: int,
    linkedin_url: str = "",
) -> dict:
    job = _require_catalog_job(company_name, job_url)
    normalized = _normalize_linkedin_url(linkedin_url) if waiting_referral else ""
    result = repo.set_waiting_referral(
        user_id, country_key, company_name, job_url, waiting_referral,
        linkedin_url=normalized, job_title=job.get("title", ""),
    )
    return _validated(result)


def set_job_ats_score(
    country_key: str,
    company_name: str,
    job_url: str,
    ats_score: int | None,
    *,
    user_id: int,
) -> dict:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    job = get_job_by_url(job_url)
    result = repo.set_ats_score(
        user_id, country_key, company_name, job_url, ats_score,
        job_title=job.get("title", "") if job else "",
    )
    return _validated(result)


def set_job_looking_to_apply(
    country_key: str,
    company_name: str,
    job_url: str,
    looking_to_apply: bool,
    *,
    user_id: int,
) -> dict:
    job = _require_catalog_job(company_name, job_url)
    result = repo.set_looking_to_apply(
        user_id, country_key, company_name, job_url, looking_to_apply,
        job_title=job.get("title", ""),
    )
    return _validated(result)


def set_job_seen(
    country_key: str,
    company_name: str,
    job_url: str,
    seen: bool = True,
    *,
    user_id: int,
) -> dict:
    job = get_job_by_url(job_url)
    result = repo.set_seen(
        user_id, country_key, company_name, job_url, seen,
        job_title=job.get("title", "") if job else "",
    )
    return _validated(result)


def set_job_not_for_me(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
    not_for_me: bool = True,
    reason: str | None = None,
) -> dict:
    _require_catalog_job(company_name, job_url)
    result = repo.set_not_for_me(
        user_id, country_key, company_name, job_url,
        not_for_me=not_for_me, reason=reason,
    )
    return _validated(result)


def reconcile_wrong_location_hides(
    user_id: int,
    *,
    country_key: str | None = None,
    city_label: str | None = None,
) -> int:
    rows = repo.load_wrong_location_hides(user_id, country_key)
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

        repo.set_not_for_me(user_id, country, company_name, job_url, not_for_me=False)
        restored += 1

    return restored
