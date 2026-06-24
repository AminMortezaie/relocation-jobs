from __future__ import annotations

from relocation_jobs.panel.types import FlattenFilters


def test_flatten_filters_maps_position_kwargs():
    filters = FlattenFilters.from_kwargs(
        country_key="uk",
        hide_position_applied=True,
        position_rejected_only=True,
    )
    assert filters.position_filters.hide_applied is True
    assert filters.position_filters.rejected_only is True
    assert filters.country_key == "uk"
