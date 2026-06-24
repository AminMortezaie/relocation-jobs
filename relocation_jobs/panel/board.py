from __future__ import annotations

from relocation_jobs.panel.service import flatten_companies


def load_catalog_board(
    country_key: str | None,
    *,
    ats_type: str | None,
    location: str | None,
    user_id: int | None,
) -> tuple[list[dict], list[dict], int]:
    return flatten_companies(
        country_key,
        visa_only=False,
        hide_applied=False,
        hide_empty=False,
        not_applied_only=False,
        hide_position_applied=False,
        hide_position_rejected=False,
        position_applied_only=False,
        position_rejected_only=False,
        position_looking_to_apply_only=False,
        fetch_ok_only=False,
        fetch_problem_only=False,
        location=location,
        city=None,
        ats_type=ats_type,
        user_id=user_id,
    )
