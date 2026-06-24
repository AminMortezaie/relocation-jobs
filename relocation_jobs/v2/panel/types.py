from __future__ import annotations

from relocation_jobs.v2.shared.schema import BaseSchema
from relocation_jobs.v2.positions.types import PositionFilters


class FlattenFilters(BaseSchema):
    country_key: str | None = None
    user_id: int | None = None
    visa_only: bool = False
    hide_applied: bool = False
    hide_empty: bool = False
    not_applied_only: bool = False
    fetch_ok_only: bool = False
    fetch_problem_only: bool = False
    location: str | None = None
    city: str | None = None
    ats_type: str | None = None
    position_filters: PositionFilters = PositionFilters()

    @property
    def location_filter(self) -> str | None:
        return (self.location or self.city or "").strip() or None

    @classmethod
    def from_kwargs(cls, **kwargs) -> FlattenFilters:
        data = dict(kwargs)
        position_arg_map = {
            "hide_position_applied": "hide_applied",
            "hide_position_rejected": "hide_rejected",
            "position_applied_only": "applied_only",
            "position_rejected_only": "rejected_only",
            "position_looking_to_apply_only": "looking_to_apply_only",
        }
        position_kwargs = {}
        for src, dest in position_arg_map.items():
            if src in data:
                position_kwargs[dest] = data.pop(src)
        return cls(position_filters=PositionFilters(**position_kwargs), **data)
