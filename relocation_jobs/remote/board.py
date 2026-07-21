from __future__ import annotations

from relocation_jobs.panel.board import (
    DEFAULT_BOARD_PAGE_SIZE,
    MAX_BOARD_PAGE_SIZE,
    load_catalog_board_page,
)
from relocation_jobs.shared.board_contract import CATALOG_KIND_REMOTE

__all__ = (
    "DEFAULT_BOARD_PAGE_SIZE",
    "MAX_BOARD_PAGE_SIZE",
    "load_remote_board_page",
)


def load_remote_board_page(
    country_key: str | None,
    *,
    ats_type: str | None,
    location: str | None,
    user_id: int | None,
    visible_offset: int,
    limit: int,
    search: str | None = None,
    panel_flags: dict | None = None,
    count_total: bool = False,
    sort: str | None = "newest",
) -> tuple[list[dict], list[dict], int, int | None, bool]:
    flags = dict(panel_flags or {})
    flags["visa_only"] = False
    return load_catalog_board_page(
        country_key,
        ats_type=ats_type,
        location=location,
        user_id=user_id,
        visible_offset=visible_offset,
        limit=limit,
        search=search,
        panel_flags=flags,
        count_total=count_total,
        sort=sort,
        catalog_kind=CATALOG_KIND_REMOTE,
    )
