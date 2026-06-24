from __future__ import annotations

from relocation_jobs.v2.positions.types import PositionBucket, PositionFilters, PositionView, TrackingFlags


def derive_bucket(
    flags: TrackingFlags,
    *,
    wrong_location: bool = False,
) -> PositionBucket:
    if flags.not_for_me or wrong_location:
        return PositionBucket.NOT_FOR_ME
    if flags.rejected:
        return PositionBucket.REJECTED
    return PositionBucket.JOBS


def orphan_reinject_eligible(flags: TrackingFlags) -> bool:
    return flags.has_active_tracking()


def position_view_from_row(
    row: dict | None,
    *,
    wrong_location: bool = False,
) -> PositionView:
    flags = TrackingFlags.from_row(row)
    return PositionView(
        flags=flags,
        bucket=derive_bucket(flags, wrong_location=wrong_location),
    )


def passes_position_filters(flags: TrackingFlags, filters: PositionFilters) -> bool:
    if filters.hide_applied and flags.applied:
        return False
    if filters.hide_rejected and flags.rejected:
        return False
    if filters.applied_only and not flags.applied:
        return False
    if filters.rejected_only and not flags.rejected:
        return False
    if filters.looking_to_apply_only and not flags.looking_to_apply:
        return False
    return True
