from __future__ import annotations

from relocation_jobs.core.location_tags import company_expected_locations, job_matches_expected_locations
from relocation_jobs.panel.flatten_orphans import stats_job_entry
from relocation_jobs.panel.tracking import catalog_not_for_me, job_dict, resolve_track, resolve_track_flags
from relocation_jobs.positions.state import (
    derive_bucket,
    effective_wrong_location,
    passes_position_filters,
    position_view_from_row,
)
from relocation_jobs.positions.types import PositionBucket, PositionFilters, TrackingFlags
from relocation_jobs.shared.coerce import as_bool


def not_for_me_entry(
    job: dict,
    *,
    company_name: str,
    company: dict,
    country_key: str,
    country_label: str,
    job_tracking: dict | None,
    status_history: dict | None,
    mcp_applications: dict | None,
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
        mcp_applications=mcp_applications,
    )
    if wrong_location:
        entry["not_for_me"] = True
        if not entry.get("not_for_me_reason"):
            entry["not_for_me_reason"] = "wrong_location"
    return entry


def job_fails_office_location_gate(job: dict, expected_locations) -> tuple[bool, str | None]:
    if not expected_locations:
        return False, None
    ok, reason = job_matches_expected_locations(job, expected_locations)
    if ok:
        return False, None
    return True, reason


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
    mcp_applications: dict | None,
    visa_only: bool,
    position_filters: PositionFilters,
) -> tuple[list[dict], list[dict], list[dict], int, int]:
    jobs: list[dict] = []
    not_for_me_jobs: list[dict] = []
    rejected_jobs: list[dict] = []
    positions_not_for_me = 0
    positions_hidden_by_visa = 0
    expected_locations = company_expected_locations(company, catalog_country=country_key)

    for job in stored_jobs:
        fails_gate, _ = job_fails_office_location_gate(job, expected_locations)

        if user_id:
            track = resolve_track(
                job_tracking, country=country_key, company_name=company_name, job=job,
            )
            wrong_location = effective_wrong_location(fails_gate=fails_gate, track=track)
            view = position_view_from_row(track, wrong_location=wrong_location)
            if view.bucket == PositionBucket.NOT_FOR_ME:
                positions_not_for_me += 1
                not_for_me_jobs.append(not_for_me_entry(
                    job,
                    company_name=company_name,
                    company=company,
                    country_key=country_key,
                    country_label=country_label,
                    job_tracking=job_tracking,
                    status_history=status_history,
                    mcp_applications=mcp_applications,
                    wrong_location=wrong_location,
                ))
                continue
        elif catalog_not_for_me(job) or fails_gate:
            positions_not_for_me += 1
            not_for_me_jobs.append(not_for_me_entry(
                job,
                company_name=company_name,
                company=company,
                country_key=country_key,
                country_label=country_label,
                job_tracking=None,
                status_history=None,
                mcp_applications=mcp_applications,
                wrong_location=fails_gate,
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
            mcp_applications=mcp_applications if user_id else None,
        )
        flags = TrackingFlags.from_job_panel_dict(job_entry)
        if derive_bucket(flags) == PositionBucket.REJECTED:
            rejected_jobs.append(job_entry)
            continue
        if not passes_position_filters(flags, position_filters):
            continue
        jobs.append(job_entry)

    return jobs, not_for_me_jobs, rejected_jobs, positions_not_for_me, positions_hidden_by_visa


def partition_stored_jobs_for_stats(
    stored_jobs: list[dict],
    *,
    user_id: int | None,
    job_tracking: dict,
    alias_index: dict[tuple[str, str, str], dict],
    company_name: str,
    company: dict,
    country_key: str,
    visa_only: bool,
    position_filters: PositionFilters,
) -> tuple[list[dict], list[dict], int]:
    jobs: list[dict] = []
    rejected_jobs: list[dict] = []
    positions_not_for_me = 0
    expected_locations = company_expected_locations(company, catalog_country=country_key)

    for job in stored_jobs:
        fails_gate, _ = job_fails_office_location_gate(job, expected_locations)
        track: dict = {}
        if user_id:
            track = resolve_track_flags(
                job_tracking,
                alias_index,
                country=country_key,
                company_name=company_name,
                job=job,
            )
            wrong_location = effective_wrong_location(fails_gate=fails_gate, track=track)
            view = position_view_from_row(track, wrong_location=wrong_location)
            if view.bucket == PositionBucket.NOT_FOR_ME:
                positions_not_for_me += 1
                continue
        elif catalog_not_for_me(job) or fails_gate:
            positions_not_for_me += 1
            continue

        if visa_only and job.get("visa_sponsorship") is not True:
            continue

        applied = bool(track.get("applied")) if user_id else bool(job.get("applied"))
        rejected = as_bool(track.get("rejected")) if user_id else as_bool(job.get("rejected"))
        flags = TrackingFlags(
            applied=applied,
            rejected=rejected,
            not_for_me=bool(track.get("not_for_me")) if user_id else bool(job.get("not_for_me")),
            looking_to_apply=bool(track.get("looking_to_apply")) if user_id else False,
        )
        if derive_bucket(flags) == PositionBucket.REJECTED:
            rejected_jobs.append(stats_job_entry(
                applied=applied,
                visa_sponsorship=job.get("visa_sponsorship"),
            ))
            continue
        if not passes_position_filters(flags, position_filters):
            continue
        jobs.append(stats_job_entry(
            applied=applied,
            visa_sponsorship=job.get("visa_sponsorship"),
            fetched=job.get("fetched", ""),
            last_seen=job.get("last_seen", ""),
        ))

    return jobs, rejected_jobs, positions_not_for_me
