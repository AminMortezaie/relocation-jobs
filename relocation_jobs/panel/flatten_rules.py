from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from relocation_jobs.core.job_identity import job_idempotency_key
from relocation_jobs.core.location_tags import (
    company_matches_location_filter,
    company_visible_for_country_filter,
)
from relocation_jobs.panel.types import FlattenFilters
from relocation_jobs.shared.coerce import as_bool
from relocation_jobs.shared.predicates import any_of


@dataclass(frozen=True)
class OrphanTrackContext:
    country_key: str
    company_name: str
    t_country: str
    t_company: str
    t_url: str
    track: dict
    listed_urls: set[str]
    listed_keys: set[str]


@dataclass(frozen=True)
class CompanySkipContext:
    company: dict
    filters: FlattenFilters
    country_key: str
    country_filter: str | None
    location_filter: str | None
    header: dict


@dataclass(frozen=True)
class CompanySkipAfterContext:
    filters: FlattenFilters
    jobs: list[dict]
    not_for_me_jobs: list[dict]
    rejected_jobs: list[dict]
    header: dict


ORPHAN_TRACK_SKIP_RULES: tuple[Callable[[OrphanTrackContext], bool], ...] = (
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


def company_ats_type(company: dict) -> str:
    return (company.get("ats_type") or "").strip() or "generic"


COMPANY_SKIP_BEFORE_RULES: tuple[Callable[[CompanySkipContext], bool], ...] = (
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
    lambda ctx: bool(ctx.filters.ats_type and company_ats_type(ctx.company) != ctx.filters.ats_type),
    lambda ctx: bool(ctx.filters.hide_applied and ctx.header["company_applied"]),
    lambda ctx: bool(
        ctx.filters.fetch_ok_only
        and not (ctx.company.get("fetch_ok") and not ctx.company.get("fetch_problem"))
    ),
    lambda ctx: bool(ctx.filters.fetch_problem_only and not ctx.company.get("fetch_problem")),
)


COMPANY_SKIP_AFTER_RULES: tuple[Callable[[CompanySkipAfterContext], bool], ...] = (
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


def skip_company_before_jobs(
    company: dict,
    *,
    filters: FlattenFilters,
    country_key: str,
    country_filter: str | None,
    location_filter: str | None,
    header: dict,
) -> bool:
    ctx = CompanySkipContext(
        company=company,
        filters=filters,
        country_key=country_key,
        country_filter=country_filter,
        location_filter=location_filter,
        header=header,
    )
    return any_of(ctx, COMPANY_SKIP_BEFORE_RULES)


def skip_company_after_jobs(
    *,
    filters: FlattenFilters,
    jobs: list[dict],
    not_for_me_jobs: list[dict],
    rejected_jobs: list[dict],
    header: dict,
) -> bool:
    ctx = CompanySkipAfterContext(
        filters=filters,
        jobs=jobs,
        not_for_me_jobs=not_for_me_jobs,
        rejected_jobs=rejected_jobs,
        header=header,
    )
    return any_of(ctx, COMPANY_SKIP_AFTER_RULES)
