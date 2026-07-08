from __future__ import annotations

from relocation_jobs.core.job_identity import job_idempotency_key, normalize_job_url
from relocation_jobs.panel.flatten_rules import ORPHAN_TRACK_SKIP_RULES, OrphanTrackContext
from relocation_jobs.panel.tracking import tracked_job_dict
from relocation_jobs.positions.state import passes_position_filters
from relocation_jobs.positions.types import PositionFilters, TrackingFlags
from relocation_jobs.shared.coerce import as_bool
from relocation_jobs.shared.predicates import any_of


def stats_job_entry(
    *,
    applied: bool,
    visa_sponsorship,
    fetched: str = "",
    last_seen: str = "",
) -> dict:
    return {
        "applied": applied,
        "visa_sponsorship": visa_sponsorship,
        "fetched": fetched,
        "last_seen": last_seen,
    }


def append_tracked_orphans(
    jobs: list[dict],
    rejected_jobs: list[dict],
    *,
    country_key: str,
    company_name: str,
    company: dict,
    country_label: str,
    job_tracking: dict,
    status_history: dict,
    mcp_applications: dict | None,
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
        ctx = OrphanTrackContext(
            country_key=country_key,
            company_name=company_name,
            t_country=t_country,
            t_company=t_company,
            t_url=t_url,
            track=track,
            listed_urls=listed_urls,
            listed_keys=listed_keys,
        )
        if any_of(ctx, ORPHAN_TRACK_SKIP_RULES):
            continue
        job_entry = tracked_job_dict(
            track,
            company_name=company_name,
            company=company,
            country_key=country_key,
            country_label=country_label,
            status_history=status_history,
            mcp_applications=mcp_applications,
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


def append_tracked_orphans_for_stats(
    jobs: list[dict],
    rejected_jobs: list[dict],
    *,
    country_key: str,
    company_name: str,
    job_tracking: dict,
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
        ctx = OrphanTrackContext(
            country_key=country_key,
            company_name=company_name,
            t_country=t_country,
            t_company=t_company,
            t_url=t_url,
            track=track,
            listed_urls=listed_urls,
            listed_keys=listed_keys,
        )
        if any_of(ctx, ORPHAN_TRACK_SKIP_RULES):
            continue
        if visa_only and track.get("visa_sponsorship") is not True:
            continue
        applied = bool(track.get("applied"))
        rejected = as_bool(track.get("rejected"))
        flags = TrackingFlags(
            applied=applied,
            rejected=rejected,
            not_for_me=bool(track.get("not_for_me")),
            looking_to_apply=bool(track.get("looking_to_apply")),
        )
        if rejected:
            rejected_jobs.append(stats_job_entry(applied=applied, visa_sponsorship=None))
            continue
        if not passes_position_filters(flags, position_filters):
            continue
        jobs.append(stats_job_entry(applied=applied, visa_sponsorship=None))
