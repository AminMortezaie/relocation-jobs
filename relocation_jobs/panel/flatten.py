from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable

from relocation_jobs.core.job_identity import job_idempotency_key, normalize_job_url
from relocation_jobs.core.location_tags import (
    company_matches_location_filter,
    company_visible_for_country_filter,
    job_fails_office_location_gate,
)
from relocation_jobs.panel.tracking import (
    catalog_not_for_me,
    job_dict,
    resolve_track,
    tracked_job_dict,
    tracking_key,
)
from relocation_jobs.panel.types import FlattenFilters
from relocation_jobs.positions.state import derive_bucket, passes_position_filters, position_view_from_row
from relocation_jobs.positions.types import PositionBucket, PositionFilters, TrackingFlags
from relocation_jobs.shared.coerce import as_bool
from relocation_jobs.shared.predicates import any_of
from relocation_jobs.shared.timestamps import company_activity_ts, job_activity_ts


@dataclass
class PanelContext:
    user_id: int | None
    job_tracking: dict = field(default_factory=dict)
    company_tracking: dict = field(default_factory=dict)
    status_history: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _OrphanTrackContext:
    country_key: str
    company_name: str
    t_country: str
    t_company: str
    t_url: str
    track: dict
    listed_urls: set[str]
    listed_keys: set[str]


@dataclass(frozen=True)
class _CompanySkipContext:
    company: dict
    filters: FlattenFilters
    country_key: str
    country_filter: str | None
    location_filter: str | None
    header: dict


@dataclass(frozen=True)
class _CompanySkipAfterContext:
    filters: FlattenFilters
    jobs: list[dict]
    not_for_me_jobs: list[dict]
    rejected_jobs: list[dict]
    header: dict


_ORPHAN_TRACK_SKIP_RULES: tuple[Callable[[_OrphanTrackContext], bool], ...] = (
    lambda ctx: ctx.t_country != ctx.country_key or ctx.t_company != ctx.company_name,
    lambda ctx: bool(ctx.track.get("not_for_me")),
    lambda ctx: not (
        ctx.track.get("applied")
        or as_bool(ctx.track.get("rejected"))
        or ctx.track.get("looking_to_apply")
    ),
    lambda ctx: ctx.t_url in ctx.listed_urls,
    lambda ctx: bool(ctx.t_url and job_idempotency_key(ctx.t_url) in ctx.listed_keys),
)


_COMPANY_SKIP_BEFORE_RULES: tuple[Callable[[_CompanySkipContext], bool], ...] = (
    lambda ctx: bool(
        ctx.country_filter
        and ctx.country_filter != "all"
        and not company_visible_for_country_filter(
            ctx.company, ctx.country_filter, catalog_country=ctx.country_key,
        )
    ),
    lambda ctx: bool(
        ctx.location_filter
        and not company_matches_location_filter(
            ctx.company, ctx.location_filter, catalog_country=ctx.country_key,
        )
    ),
    lambda ctx: bool(ctx.filters.ats_type and _company_ats_type(ctx.company) != ctx.filters.ats_type),
    lambda ctx: bool(ctx.filters.hide_applied and ctx.header["company_applied"]),
    lambda ctx: bool(
        ctx.filters.fetch_ok_only
        and not (ctx.company.get("fetch_ok") and not ctx.company.get("fetch_problem"))
    ),
    lambda ctx: bool(ctx.filters.fetch_problem_only and not ctx.company.get("fetch_problem")),
)


_COMPANY_SKIP_AFTER_RULES: tuple[Callable[[_CompanySkipAfterContext], bool], ...] = (
    lambda ctx: bool(ctx.filters.visa_only and not ctx.jobs and not ctx.rejected_jobs),
    lambda ctx: bool(ctx.filters.position_filters.rejected_only and not ctx.rejected_jobs),
    lambda ctx: bool(
        (ctx.filters.position_filters.applied_only or ctx.filters.position_filters.looking_to_apply_only)
        and not ctx.jobs
    ),
    lambda ctx: bool(
        ctx.filters.hide_empty
        and not ctx.jobs
        and not (ctx.filters.position_filters.rejected_only and ctx.rejected_jobs)
    ),
    lambda ctx: bool(ctx.filters.not_applied_only and (ctx.header["company_applied"] or not ctx.jobs)),
)


def _company_ats_type(company: dict) -> str:
    return (company.get("ats_type") or "").strip() or "generic"


def _not_for_me_entry(
    job: dict,
    *,
    company_name: str,
    company: dict,
    country_key: str,
    country_label: str,
    job_tracking: dict | None,
    status_history: dict | None,
    wrong_location: bool,
) -> dict:
    entry = job_dict(
        job,
        company_name=company_name,
        company=company,
        country_key=country_key,
        country_label=country_label,
        job_tracking=job_tracking,
        status_history=status_history,
    )
    if wrong_location:
        entry["not_for_me"] = True
        if not entry.get("not_for_me_reason"):
            entry["not_for_me_reason"] = "wrong_location"
    return entry


def partition_stored_jobs(
    stored_jobs: list[dict],
    *,
    user_id: int | None,
    job_tracking: dict,
    company_name: str,
    company: dict,
    country_key: str,
    country_label: str,
    status_history: dict,
    visa_only: bool,
    position_filters: PositionFilters,
) -> tuple[list[dict], list[dict], list[dict], int, int]:
    jobs: list[dict] = []
    not_for_me_jobs: list[dict] = []
    rejected_jobs: list[dict] = []
    positions_not_for_me = 0
    positions_hidden_by_visa = 0

    for job in stored_jobs:
        fails_gate, _ = job_fails_office_location_gate(job, company, catalog_country=country_key)
        wrong_location = fails_gate

        if user_id:
            track = resolve_track(
                job_tracking, country=country_key, company_name=company_name, job=job,
            )
            view = position_view_from_row(track, wrong_location=wrong_location)
            if view.bucket == PositionBucket.NOT_FOR_ME:
                positions_not_for_me += 1
                not_for_me_jobs.append(_not_for_me_entry(
                    job,
                    company_name=company_name,
                    company=company,
                    country_key=country_key,
                    country_label=country_label,
                    job_tracking=job_tracking,
                    status_history=status_history,
                    wrong_location=wrong_location,
                ))
                continue
        elif catalog_not_for_me(job) or wrong_location:
            positions_not_for_me += 1
            not_for_me_jobs.append(_not_for_me_entry(
                job,
                company_name=company_name,
                company=company,
                country_key=country_key,
                country_label=country_label,
                job_tracking=None,
                status_history=None,
                wrong_location=wrong_location,
            ))
            continue

        if visa_only and job.get("visa_sponsorship") is not True:
            positions_hidden_by_visa += 1
            continue

        job_entry = job_dict(
            job,
            company_name=company_name,
            company=company,
            country_key=country_key,
            country_label=country_label,
            job_tracking=job_tracking if user_id else None,
            status_history=status_history if user_id else None,
        )
        flags = TrackingFlags.from_job_panel_dict(job_entry)
        if derive_bucket(flags) == PositionBucket.REJECTED:
            rejected_jobs.append(job_entry)
            continue
        if not passes_position_filters(flags, position_filters):
            continue
        jobs.append(job_entry)

    return jobs, not_for_me_jobs, rejected_jobs, positions_not_for_me, positions_hidden_by_visa


def _append_tracked_orphans(
    jobs: list[dict],
    rejected_jobs: list[dict],
    *,
    country_key: str,
    company_name: str,
    company: dict,
    country_label: str,
    job_tracking: dict,
    status_history: dict,
    visa_only: bool,
    position_filters: PositionFilters,
) -> None:
    listed_urls = {normalize_job_url(j.get("url", "")) for j in jobs}
    listed_urls.update(normalize_job_url(j.get("url", "")) for j in rejected_jobs)
    listed_keys = {job_idempotency_key(j.get("url", "")) for j in jobs if j.get("url")}
    listed_keys.update(
        job_idempotency_key(j.get("url", "")) for j in rejected_jobs if j.get("url")
    )
    listed_keys.discard("")
    for (t_country, t_company, t_url), track in job_tracking.items():
        ctx = _OrphanTrackContext(
            country_key=country_key,
            company_name=company_name,
            t_country=t_country,
            t_company=t_company,
            t_url=t_url,
            track=track,
            listed_urls=listed_urls,
            listed_keys=listed_keys,
        )
        if any_of(ctx, _ORPHAN_TRACK_SKIP_RULES):
            continue
        job_entry = tracked_job_dict(
            track,
            company_name=company_name,
            company=company,
            country_key=country_key,
            country_label=country_label,
            status_history=status_history,
        )
        if visa_only and job_entry.get("visa_sponsorship") is not True:
            continue
        if job_entry.get("rejected"):
            rejected_jobs.append(job_entry)
            continue
        flags = TrackingFlags.from_job_panel_dict(job_entry)
        if not passes_position_filters(flags, position_filters):
            continue
        jobs.append(job_entry)


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
    return {
        "company_applied": applied,
        "company_applied_date": applied_date,
        "positions_applied_all": positions,
        "company_applied_at": applied_at,
        "awaiting_response": awaiting,
        "awaiting_response_date": awaiting_date,
    }


def _skip_company_before_jobs(
    company: dict,
    *,
    filters: FlattenFilters,
    country_key: str,
    country_filter: str | None,
    location_filter: str | None,
    header: dict,
) -> bool:
    ctx = _CompanySkipContext(
        company=company,
        filters=filters,
        country_key=country_key,
        country_filter=country_filter,
        location_filter=location_filter,
        header=header,
    )
    return any_of(ctx, _COMPANY_SKIP_BEFORE_RULES)


def _skip_company_after_jobs(
    *,
    filters: FlattenFilters,
    jobs: list[dict],
    not_for_me_jobs: list[dict],
    rejected_jobs: list[dict],
    header: dict,
) -> bool:
    ctx = _CompanySkipAfterContext(
        filters=filters,
        jobs=jobs,
        not_for_me_jobs=not_for_me_jobs,
        rejected_jobs=rejected_jobs,
        header=header,
    )
    return any_of(ctx, _COMPANY_SKIP_AFTER_RULES)


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
    stored_jobs = company.get("matching_jobs") or []
    sort_ts = company_activity_ts(company, stored_jobs)
    visible_ts = [job_activity_ts(j) for j in jobs if job_activity_ts(j)]
    latest_fetch = max(visible_ts, default="") or sort_ts
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
        "jobs": jobs,
        "not_for_me_jobs": not_for_me_jobs,
        "rejected_jobs": rejected_jobs,
        "job_count": len(jobs),
        "stored_job_count": stored_job_count,
        "positions_applied": positions_applied,
        "positions_applied_all": header["positions_applied_all"] if user_id else positions_applied,
        "positions_rejected": len(rejected_jobs),
        "positions_not_for_me": positions_not_for_me,
        "positions_hidden_by_visa": positions_hidden_by_visa,
        "updated": company.get("updated", ""),
        "latest_fetched": latest_fetch,
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
        visa_only=filters.visa_only,
        position_filters=filters.position_filters,
    )
    if ctx.user_id:
        _append_tracked_orphans(
            jobs,
            rejected,
            country_key=country_key,
            company_name=company_name,
            company=company,
            country_label=country_label,
            job_tracking=ctx.job_tracking,
            status_history=ctx.status_history,
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
    if _skip_company_before_jobs(
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
    if _skip_company_after_jobs(
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
