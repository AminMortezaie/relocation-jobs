from __future__ import annotations

from relocation_jobs.positions.state import (
    derive_bucket,
    orphan_reinject_eligible,
    passes_position_filters,
    position_view_from_row,
)
from relocation_jobs.positions.types import PositionBucket, PositionFilters, TrackingFlags


def test_derive_bucket_main_board():
    flags = TrackingFlags()
    assert derive_bucket(flags) == PositionBucket.JOBS


def test_derive_bucket_rejected_over_applied():
    flags = TrackingFlags(rejected=True, applied=True)
    assert derive_bucket(flags) == PositionBucket.REJECTED


def test_derive_bucket_not_for_me_over_rejected():
    flags = TrackingFlags(not_for_me=True, rejected=True)
    assert derive_bucket(flags) == PositionBucket.NOT_FOR_ME


def test_derive_bucket_wrong_location():
    flags = TrackingFlags()
    assert derive_bucket(flags, wrong_location=True) == PositionBucket.NOT_FOR_ME


def test_orphan_reinject_skips_not_for_me():
    flags = TrackingFlags(not_for_me=True, applied=True)
    assert orphan_reinject_eligible(flags) is False


def test_orphan_reinject_when_applied():
    flags = TrackingFlags(applied=True)
    assert orphan_reinject_eligible(flags) is True


def test_position_filters_hide_applied():
    flags = TrackingFlags(applied=True)
    filters = PositionFilters(hide_applied=True)
    assert passes_position_filters(flags, filters) is False


def test_position_filters_applied_only():
    assert passes_position_filters(TrackingFlags(), PositionFilters(applied_only=True)) is False
    assert passes_position_filters(TrackingFlags(applied=True), PositionFilters(applied_only=True)) is True


def test_position_view_from_row():
    view = position_view_from_row({"applied": 1, "rejected": 0, "not_for_me": 0})
    assert view.flags.applied is True
    assert view.bucket == PositionBucket.JOBS
    assert view.on_main_board is True


def test_position_view_wrong_location():
    view = position_view_from_row(None, wrong_location=True)
    assert view.bucket == PositionBucket.NOT_FOR_ME
    assert view.on_main_board is False
