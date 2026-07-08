from __future__ import annotations

from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.users import applied as applied_queries


def _list_recent_fetch_runs(user_id: int, country_key: str | None) -> list[dict]:
    if country_key and country_key != "all":
        return fetch_repo.list_user_fetch_runs(user_id, country=country_key, limit=5)
    return fetch_repo.list_user_fetch_runs(user_id, limit=5)


def _actionable_open_job(job: dict) -> bool:
    return not job.get("applied") and not job.get("not_for_me")


def _count_open_roles(companies: list[dict]) -> int:
    return sum(
        1
        for company in companies
        for job in company.get("jobs") or []
        if _actionable_open_job(job)
    )


def _count_companies_with_open_roles(companies: list[dict]) -> int:
    return sum(
        1
        for company in companies
        if any(_actionable_open_job(job) for job in company.get("jobs") or [])
    )


def _count_visa_open_roles(companies: list[dict]) -> int:
    return sum(
        1
        for company in companies
        for job in company.get("jobs") or []
        if job.get("visa_sponsorship") is True and _actionable_open_job(job)
    )


def _count_not_for_me_roles(companies: list[dict]) -> int:
    return sum(int(company.get("positions_not_for_me") or 0) for company in companies)


def resolve_new_jobs_count(
    *,
    user_id: int | None,
    country_key: str | None,
    timezone_name: str | None,
    file_meta: list[dict],
) -> int:
    if user_id:
        return fetch_repo.sum_new_jobs_today(
            user_id,
            country=country_key,
            timezone_name=timezone_name,
        )
    return sum(int(m.get("last_fetch_new_jobs") or 0) for m in file_meta)


def compute_view_stats(
    companies: list[dict],
    *,
    fetch_problem_count: int = 0,
    latest_fetch_new_jobs: int = 0,
) -> dict:
    open_roles = _count_open_roles(companies)
    visa_count = _count_visa_open_roles(companies)
    positions_rejected = sum(c.get("positions_rejected", 0) for c in companies)
    positions_not_for_me = _count_not_for_me_roles(companies)
    latest_fetch = max(
        (c.get("newest_job_fetched") or c.get("latest_fetched") or "" for c in companies),
        default="",
    )
    by_country: dict[str, int] = {}
    for company in companies:
        key = company["country"]
        by_country[key] = by_country.get(key, 0) + sum(
            1 for job in company.get("jobs") or [] if _actionable_open_job(job)
        )
    return {
        "total_jobs": open_roles,
        "companies_with_jobs": _count_companies_with_open_roles(companies),
        "visa_sponsored": visa_count,
        "positions_rejected": positions_rejected,
        "positions_not_for_me": positions_not_for_me,
        "fetch_problems": fetch_problem_count,
        "latest_job_fetch": latest_fetch,
        "latest_fetch_new_jobs": latest_fetch_new_jobs,
        "by_country": by_country,
    }


def compute_user_board_stats(
    *,
    user_id: int | None,
    country_key: str | None,
    timezone_name: str | None,
    latest_fetch_new_jobs: int = 0,
) -> dict:
    positions_applied = (
        applied_queries.count_jobs_applied(user_id, country=country_key)
        if user_id else 0
    )
    positions_applied_today = (
        applied_queries.count_jobs_applied_today(
            user_id, country=country_key, timezone_name=timezone_name,
        )
        if user_id else 0
    )
    applied_today_jobs = (
        applied_queries.list_jobs_applied_today(
            user_id, country=country_key, timezone_name=timezone_name,
        )
        if user_id else []
    )
    recent_fetch_runs = (
        _list_recent_fetch_runs(user_id, country_key)
        if user_id else []
    )
    return {
        "applied": 0,
        "positions_applied": positions_applied,
        "positions_applied_today": positions_applied_today,
        "applied_today_jobs": applied_today_jobs,
        "recent_fetch_runs": recent_fetch_runs,
        "latest_fetch_new_jobs": latest_fetch_new_jobs,
    }


def compute_stats(
    companies: list[dict],
    file_meta: list[dict],
    *,
    fetch_problem_count: int = 0,
    user_id: int | None = None,
    country_key: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    open_roles = _count_open_roles(companies)
    visa_count = _count_visa_open_roles(companies)
    positions_applied = (
        applied_queries.count_jobs_applied(user_id, country=country_key)
        if user_id
        else sum(c.get("positions_applied_all", c.get("positions_applied", 0)) for c in companies)
    )
    positions_rejected = sum(c.get("positions_rejected", 0) for c in companies)
    positions_not_for_me = _count_not_for_me_roles(companies)
    company_applied_count = sum(
        1 for c in companies if c.get("company_applied") or c.get("positions_applied_all", 0) > 0
    )
    latest_fetch = max(
        (c.get("newest_job_fetched") or c.get("latest_fetched") or "" for c in companies),
        default="",
    )
    latest_fetch_new_jobs = resolve_new_jobs_count(
        user_id=user_id,
        country_key=country_key,
        timezone_name=timezone_name,
        file_meta=file_meta,
    )
    positions_applied_today = (
        applied_queries.count_jobs_applied_today(
            user_id, country=country_key, timezone_name=timezone_name,
        )
        if user_id else 0
    )
    applied_today_jobs = (
        applied_queries.list_jobs_applied_today(
            user_id, country=country_key, timezone_name=timezone_name,
        )
        if user_id else 0
    )
    recent_fetch_runs = (
        _list_recent_fetch_runs(user_id, country_key)
        if user_id else []
    )
    by_country: dict[str, int] = {}
    for company in companies:
        key = company["country"]
        by_country[key] = by_country.get(key, 0) + sum(
            1 for job in company.get("jobs") or [] if _actionable_open_job(job)
        )
    return {
        "total_jobs": open_roles,
        "companies_with_jobs": _count_companies_with_open_roles(companies),
        "visa_sponsored": visa_count,
        "applied": company_applied_count,
        "positions_applied": positions_applied,
        "positions_applied_today": positions_applied_today,
        "applied_today_jobs": applied_today_jobs,
        "positions_rejected": positions_rejected,
        "positions_not_for_me": positions_not_for_me,
        "fetch_problems": fetch_problem_count,
        "latest_job_fetch": latest_fetch,
        "latest_fetch_new_jobs": latest_fetch_new_jobs,
        "recent_fetch_runs": recent_fetch_runs,
        "by_country": by_country,
        "files": file_meta,
    }
