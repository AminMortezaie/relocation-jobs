"""Job tracking business logic.

Coordinates the catalog (find_job_in_data) with the job repository (db/tracking.py).
No raw SQL here — all DB access goes through db/.
"""

from __future__ import annotations

from urllib.parse import urlparse

from relocation_jobs.db import (
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


def _load_country(country_key: str) -> dict:
    from relocation_jobs.services.catalog_service import _load_country_data
    return _load_country_data(country_key) or {}


def _find_job(data: dict, company_name: str, job_url: str):
    from relocation_jobs.services.company_service import find_job_in_data
    return find_job_in_data(data, company_name, job_url)


def _find_company(data: dict, company_name: str):
    from relocation_jobs.services.company_service import find_company_in_data
    return find_company_in_data(data, company_name)


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
    data = _load_country(country_key)
    job = _find_job(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    result = set_job_applied_db(
        user_id,
        country_key,
        company_name,
        job_url,
        applied,
        job_title=job.get("title", ""),
    )
    sync_company_applied_from_jobs_db(user_id, country_key, company_name)
    if applied:
        set_company_awaiting_response_db(
            user_id,
            country_key,
            company_name,
            True,
            preserve_date=True,
        )
    return result


def set_job_rejected(
    country_key: str,
    company_name: str,
    job_url: str,
    rejected: bool,
    *,
    user_id: int,
) -> dict:
    data = _load_country(country_key)
    job = _find_job(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return set_job_rejected_db(
        user_id,
        country_key,
        company_name,
        job_url,
        rejected,
        job_title=job.get("title", ""),
    )


def set_job_reapply(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
) -> dict:
    data = _load_country(country_key)
    job = _find_job(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return reapply_job_db(user_id, country_key, company_name, job_url)


def set_job_waiting_referral(
    country_key: str,
    company_name: str,
    job_url: str,
    waiting_referral: bool,
    *,
    user_id: int,
    linkedin_url: str = "",
) -> dict:
    data = _load_country(country_key)
    job = _find_job(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    normalized_linkedin = _normalize_linkedin(linkedin_url) if waiting_referral else ""
    return set_job_waiting_referral_db(
        user_id,
        country_key,
        company_name,
        job_url,
        waiting_referral,
        linkedin_url=normalized_linkedin,
        job_title=job.get("title", ""),
    )


def set_job_ats_score(
    country_key: str,
    company_name: str,
    job_url: str,
    ats_score: int | None,
    *,
    user_id: int,
) -> dict:
    data = _load_country(country_key)
    if _find_company(data, company_name) is None:
        raise LookupError(f"Company not found: {company_name}")
    job = _find_job(data, company_name, job_url)
    title = job.get("title", "") if job else ""
    return set_job_ats_score_db(
        user_id,
        country_key,
        company_name,
        job_url,
        ats_score,
        job_title=title,
    )


def set_job_looking_to_apply(
    country_key: str,
    company_name: str,
    job_url: str,
    looking_to_apply: bool,
    *,
    user_id: int,
) -> dict:
    data = _load_country(country_key)
    job = _find_job(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return set_job_looking_to_apply_db(
        user_id,
        country_key,
        company_name,
        job_url,
        looking_to_apply,
        job_title=job.get("title", ""),
    )


def set_job_seen(
    country_key: str,
    company_name: str,
    job_url: str,
    seen: bool = True,
    *,
    user_id: int,
) -> dict:
    data = _load_country(country_key)
    job = _find_job(data, company_name, job_url)
    return set_job_seen_db(
        user_id,
        country_key,
        company_name,
        job_url,
        seen,
        job_title=job.get("title", "") if job else "",
    )


def set_job_not_for_me(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
    not_for_me: bool = True,
    reason: str | None = None,
) -> dict:
    data = _load_country(country_key)
    job = _find_job(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return set_job_not_for_me_db(
        user_id,
        country_key,
        company_name,
        job_url,
        not_for_me=not_for_me,
        reason=reason,
    )


def reconcile_wrong_location_hides(
    user_id: int,
    *,
    country_key: str | None = None,
    city_label: str | None = None,
) -> int:
    from relocation_jobs.db import get_connection
    from relocation_jobs.location_tags import city_match_keys, company_expected_locations, job_matches_expected_locations
    from relocation_jobs.services.catalog_service import _load_country_data
    from relocation_jobs.services.company_service import find_company_in_data, find_job_in_data

    query = """
        SELECT country, company_name, job_url
        FROM job_tracking
        WHERE user_id = %s
          AND not_for_me = 1
          AND not_for_me_reason = 'wrong_location'
    """
    params: list = [user_id]
    if country_key:
        query += " AND country = %s"
        params.append(country_key)

    rows = get_connection().execute(query, params).fetchall()
    target_city_keys = city_match_keys(city_label) if city_label else set()
    restored = 0

    for row in rows:
        country = row["country"]
        company_name = row["company_name"]
        job_url = row["job_url"]

        data = _load_country_data(country)
        if not data:
            continue
        company = find_company_in_data(data, company_name)
        if company is None:
            continue
        job = find_job_in_data(data, company_name, job_url)
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
