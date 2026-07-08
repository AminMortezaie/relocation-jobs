from __future__ import annotations

from dataclasses import dataclass, field

from relocation_jobs.core.job_identity import normalize_job_url
from relocation_jobs.core.location_tags import company_visible_for_country_filter
from relocation_jobs.panel.flatten_jobs import partition_stored_jobs, partition_stored_jobs_for_stats
from relocation_jobs.panel.flatten_orphans import append_tracked_orphans, append_tracked_orphans_for_stats
from relocation_jobs.panel.flatten_rules import skip_company_after_jobs, skip_company_before_jobs
from relocation_jobs.panel.tracking import tracking_key
from relocation_jobs.panel.types import FlattenFilters
from relocation_jobs.shared.timestamps import company_newest_job_fetched


@dataclass
class PanelContext:
    user_id: int | None
    job_tracking: dict = field(default_factory=dict)
    company_tracking: dict = field(default_factory=dict)
    status_history: dict = field(default_factory=dict)
    mcp_applications: dict = field(default_factory=dict)


def sort_pinned_jobs_first(jobs: list[dict]) -> list[dict]:
    if not jobs:
        return jobs
    pinned = [job for job in jobs if job.get("pinned")]
    rest = [job for job in jobs if not job.get("pinned")]
    pinned.sort(key=lambda job: (job.get("pinned_at") or ""), reverse=True)
    return pinned + rest


def _derive_company_applied(
    country_key: str,
    company_name: str,
    stored_jobs: list[dict],
    job_tracking: dict,
) -> tuple[bool, str, int, str]:
    dates: list[str] = []
    applied_ats: list[str] = []
    seen_urls: set[str] = set()

    for job in stored_jobs:
        url = normalize_job_url(job.get("url", ""))
        seen_urls.add(url)
        track = job_tracking.get(tracking_key(country_key, company_name, url), {})
        if track.get("applied"):
            dates.append((track.get("applied_date") or "").strip())
            applied_at = (track.get("updated_at") or "").strip()
            if applied_at:
                applied_ats.append(applied_at)

    for (t_country, t_company, t_url), track in job_tracking.items():
        if t_country != country_key or t_company != company_name or t_url in seen_urls:
            continue
        if track.get("applied"):
            dates.append((track.get("applied_date") or "").strip())
            applied_at = (track.get("updated_at") or "").strip()
            if applied_at:
                applied_ats.append(applied_at)

    if not dates:
        return False, "", 0, ""

    non_empty = [d for d in dates if d]
    return True, min(non_empty), len(dates), min(applied_ats) if applied_ats else ""


def _company_header_state(
    *,
    user_id: int | None,
    country_key: str,
    company_name: str,
    company: dict,
    stored_jobs: list[dict],
    job_tracking: dict,
    company_tracking: dict,
) -> dict:
    if user_id:
        applied, applied_date, positions, applied_at = _derive_company_applied(
            country_key, company_name, stored_jobs, job_tracking,
        )
    else:
        applied = bool(company.get("company_applied"))
        applied_date = company.get("company_applied_date", "") if applied else ""
        positions, applied_at = 0, ""

    track = company_tracking.get((country_key, company_name), {})
    awaiting = bool(track.get("awaiting_response")) if user_id else False
    awaiting_date = (track.get("awaiting_response_date") or "").strip() if awaiting and user_id else ""
    board_pinned = bool(track.get("board_pinned")) if user_id else False
    board_pinned_at = (track.get("board_pinned_at") or "").strip() if board_pinned and user_id else ""
    return {
        "company_applied": applied,
        "company_applied_date": applied_date,
        "positions_applied_all": positions,
        "company_applied_at": applied_at,
        "awaiting_response": awaiting,
        "awaiting_response_date": awaiting_date,
        "board_pinned": board_pinned,
        "board_pinned_at": board_pinned_at,
    }


def _build_company_row(
    company: dict,
    *,
    company_name: str,
    country_key: str,
    country_label: str,
    header: dict,
    jobs: list[dict],
    not_for_me_jobs: list[dict],
    rejected_jobs: list[dict],
    stored_job_count: int,
    positions_not_for_me: int,
    positions_hidden_by_visa: int,
    user_id: int | None,
) -> dict:
    sort_ts = company_newest_job_fetched(jobs, company)
    positions_applied = sum(1 for j in jobs if j.get("applied"))
    return {
        "name": company_name,
        "city": company.get("city", ""),
        "cities": company.get("cities") or [],
        "locations": company.get("locations") or [],
        "size": company.get("size", ""),
        "country": country_key,
        "country_label": country_label,
        "careers_url": company.get("careers_url", ""),
        "ats_type": company.get("ats_type", ""),
        "ats_url": company.get("ats_url", ""),
        "fetch_problem": bool(company.get("fetch_problem")),
        "fetch_problem_date": company.get("fetch_problem_date", ""),
        "fetch_ok": bool(company.get("fetch_ok")),
        "fetch_ok_date": company.get("fetch_ok_date", ""),
        "company_applied": header["company_applied"],
        "company_applied_date": header["company_applied_date"],
        "company_applied_at": header["company_applied_at"],
        "awaiting_response": header["awaiting_response"],
        "awaiting_response_date": header["awaiting_response_date"],
        "board_pinned": header.get("board_pinned", False),
        "board_pinned_at": header.get("board_pinned_at", ""),
        "jobs": sort_pinned_jobs_first(jobs),
        "not_for_me_jobs": sort_pinned_jobs_first(not_for_me_jobs),
        "rejected_jobs": sort_pinned_jobs_first(rejected_jobs),
        "job_count": len(jobs),
        "stored_job_count": stored_job_count,
        "positions_applied": positions_applied,
        "positions_applied_all": header["positions_applied_all"] if user_id else positions_applied,
        "positions_rejected": len(rejected_jobs),
        "positions_not_for_me": positions_not_for_me,
        "positions_hidden_by_visa": positions_hidden_by_visa,
        "updated": company.get("updated", ""),
        "latest_fetched": sort_ts,
        "newest_job_fetched": sort_ts,
    }


def _visible_jobs(
    *,
    stored_jobs: list[dict],
    ctx: PanelContext,
    company_name: str,
    company: dict,
    country_key: str,
    country_label: str,
    filters: FlattenFilters,
) -> tuple[list[dict], list[dict], list[dict], int, int]:
    jobs, not_for_me, rejected, nfm_count, hidden = partition_stored_jobs(
        stored_jobs,
        user_id=ctx.user_id,
        job_tracking=ctx.job_tracking,
        company_name=company_name,
        company=company,
        country_key=country_key,
        country_label=country_label,
        status_history=ctx.status_history,
        mcp_applications=ctx.mcp_applications,
        visa_only=filters.visa_only,
        position_filters=filters.position_filters,
    )
    if ctx.user_id:
        append_tracked_orphans(
            jobs,
            rejected,
            country_key=country_key,
            company_name=company_name,
            company=company,
            country_label=country_label,
            job_tracking=ctx.job_tracking,
            status_history=ctx.status_history,
            mcp_applications=ctx.mcp_applications,
            visa_only=filters.visa_only,
            position_filters=filters.position_filters,
        )
    return jobs, not_for_me, rejected, nfm_count, hidden


def flatten_company(
    company: dict,
    *,
    country_key: str,
    country_label: str,
    filters: FlattenFilters,
    ctx: PanelContext,
) -> dict | None:
    company_name = company.get("name", "")
    if filters.country_key and filters.country_key != "all":
        if not company_visible_for_country_filter(
            company, filters.country_key, catalog_country=country_key,
        ):
            return None

    stored_jobs = company.get("matching_jobs") or []
    header = _company_header_state(
        user_id=ctx.user_id,
        country_key=country_key,
        company_name=company_name,
        company=company,
        stored_jobs=stored_jobs,
        job_tracking=ctx.job_tracking,
        company_tracking=ctx.company_tracking,
    )
    if skip_company_before_jobs(
        company,
        filters=filters,
        country_key=country_key,
        country_filter=filters.country_key,
        location_filter=filters.location_filter,
        header=header,
    ):
        return None

    jobs, not_for_me, rejected, nfm_count, hidden = _visible_jobs(
        stored_jobs=stored_jobs,
        ctx=ctx,
        company_name=company_name,
        company=company,
        country_key=country_key,
        country_label=country_label,
        filters=filters,
    )
    if skip_company_after_jobs(
        filters=filters,
        jobs=jobs,
        not_for_me_jobs=not_for_me,
        rejected_jobs=rejected,
        header=header,
    ):
        return None

    return _build_company_row(
        company,
        company_name=company_name,
        country_key=country_key,
        country_label=country_label,
        header=header,
        jobs=jobs,
        not_for_me_jobs=not_for_me,
        rejected_jobs=rejected,
        stored_job_count=len(stored_jobs),
        positions_not_for_me=nfm_count,
        positions_hidden_by_visa=hidden,
        user_id=ctx.user_id,
    )


def preview_board_company(
    company: dict,
    *,
    country_key: str,
    country_label: str,
    filters: FlattenFilters,
    ctx: PanelContext,
) -> tuple[str, str, dict] | None:
    company_name = company.get("name", "")
    if filters.country_key and filters.country_key != "all":
        if not company_visible_for_country_filter(
            company, filters.country_key, catalog_country=country_key,
        ):
            return None

    stored_jobs = company.get("matching_jobs") or []
    header = _company_header_state(
        user_id=ctx.user_id,
        country_key=country_key,
        company_name=company_name,
        company=company,
        stored_jobs=stored_jobs,
        job_tracking=ctx.job_tracking,
        company_tracking=ctx.company_tracking,
    )
    if skip_company_before_jobs(
        company,
        filters=filters,
        country_key=country_key,
        country_filter=filters.country_key,
        location_filter=filters.location_filter,
        header=header,
    ):
        return None

    jobs, not_for_me, rejected, _nfm_count, _hidden = _visible_jobs(
        stored_jobs=stored_jobs,
        ctx=ctx,
        company_name=company_name,
        company=company,
        country_key=country_key,
        country_label=country_label,
        filters=filters,
    )
    if skip_company_after_jobs(
        filters=filters,
        jobs=jobs,
        not_for_me_jobs=not_for_me,
        rejected_jobs=rejected,
        header=header,
    ):
        return None

    sort_ts = company_newest_job_fetched(jobs, company)
    return sort_ts, country_key, company


def summarize_company_for_stats(
    company: dict,
    *,
    country_key: str,
    filters: FlattenFilters,
    ctx: PanelContext,
    alias_index: dict[tuple[str, str, str], dict],
) -> dict | None:
    company_name = company.get("name", "")
    if filters.country_key and filters.country_key != "all":
        if not company_visible_for_country_filter(
            company, filters.country_key, catalog_country=country_key,
        ):
            return None

    stored_jobs = company.get("matching_jobs") or []
    header = _company_header_state(
        user_id=ctx.user_id,
        country_key=country_key,
        company_name=company_name,
        company=company,
        stored_jobs=stored_jobs,
        job_tracking=ctx.job_tracking,
        company_tracking=ctx.company_tracking,
    )
    if skip_company_before_jobs(
        company,
        filters=filters,
        country_key=country_key,
        country_filter=filters.country_key,
        location_filter=filters.location_filter,
        header=header,
    ):
        return None

    jobs, rejected, not_for_me_count = partition_stored_jobs_for_stats(
        stored_jobs,
        user_id=ctx.user_id,
        job_tracking=ctx.job_tracking,
        alias_index=alias_index,
        company_name=company_name,
        company=company,
        country_key=country_key,
        visa_only=filters.visa_only,
        position_filters=filters.position_filters,
    )
    if ctx.user_id:
        append_tracked_orphans_for_stats(
            jobs,
            rejected,
            country_key=country_key,
            company_name=company_name,
            job_tracking=ctx.job_tracking,
            visa_only=filters.visa_only,
            position_filters=filters.position_filters,
        )
    if skip_company_after_jobs(
        filters=filters,
        jobs=jobs,
        not_for_me_jobs=[],
        rejected_jobs=rejected,
        header=header,
    ):
        return None

    sort_ts = company_newest_job_fetched(jobs, company)
    return {
        "country": country_key,
        "jobs": jobs,
        "positions_rejected": len(rejected),
        "positions_not_for_me": not_for_me_count,
        "company_applied": header["company_applied"],
        "positions_applied_all": header["positions_applied_all"],
        "newest_job_fetched": sort_ts,
        "latest_fetched": sort_ts,
    }
