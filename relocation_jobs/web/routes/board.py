from __future__ import annotations

import math

from flask import g, jsonify, request

from relocation_jobs.core.auth import login_required
from relocation_jobs.panel.board import (
    DEFAULT_BOARD_PAGE_SIZE,
    MAX_BOARD_PAGE_SIZE,
    load_catalog_board_page,
)
from relocation_jobs.panel.stats import compute_user_board_stats
from relocation_jobs.web.query import catalog_scope_flags, query_flags


def _latest_fetch_new_jobs(file_meta: list[dict]) -> int:
    return sum(int(row.get("last_fetch_new_jobs") or 0) for row in file_meta)


def _panel_flags() -> dict:
    flags = query_flags()
    return {
        "visa_only": flags["visa_only"],
        "hide_applied": flags["hide_applied"],
        "hide_empty": flags["hide_empty"],
        "not_applied_only": flags["not_applied_only"],
        "hide_position_applied": flags["hide_position_applied"],
        "hide_position_rejected": flags["hide_position_rejected"],
        "position_applied_only": flags["position_applied_only"],
        "position_rejected_only": flags["position_rejected_only"],
        "position_looking_to_apply_only": flags["position_looking_to_apply_only"],
        "fetch_ok_only": flags["fetch_ok_only"],
        "fetch_problem_only": flags["fetch_problem_only"],
    }


def register(app):
    @app.get("/api/board")
    @login_required
    def api_board():
        scope = catalog_scope_flags()
        timezone_name = (request.args.get("timezone") or "").strip() or None
        search = (request.args.get("q") or "").strip() or None
        page = max(request.args.get("page", 1, type=int) or 1, 1)
        page_size = request.args.get("page_size", DEFAULT_BOARD_PAGE_SIZE, type=int) or DEFAULT_BOARD_PAGE_SIZE
        page_size = max(1, min(page_size, MAX_BOARD_PAGE_SIZE))
        visible_offset = (page - 1) * page_size

        companies, file_meta, fetch_problem_count, total_visible, has_more = load_catalog_board_page(
            scope["country_key"],
            ats_type=scope["ats_type"],
            location=scope["location"],
            user_id=g.user_id,
            visible_offset=visible_offset,
            limit=page_size,
            search=search,
            panel_flags=_panel_flags(),
            count_total=(page == 1),
        )
        latest_fetch_new_jobs = _latest_fetch_new_jobs(file_meta)
        total_pages = None
        if total_visible is not None:
            total_pages = max(1, math.ceil(total_visible / page_size))
        return jsonify({
            "companies": companies,
            "meta": {
                "country": request.args.get("country", "all"),
                "ats_type": scope["ats_type"],
                "location": scope["location"],
                "fetch_problem_total": fetch_problem_count,
                "latest_fetch_new_jobs": latest_fetch_new_jobs,
                "page": page,
                "page_size": page_size,
                "total_companies": total_visible,
                "total_pages": total_pages,
                "has_more": has_more,
            },
            "user_stats": compute_user_board_stats(
                user_id=g.user_id,
                country_key=scope["country_key"],
                timezone_name=timezone_name,
                latest_fetch_new_jobs=latest_fetch_new_jobs,
            ),
        })

    @app.get("/api/board/stats")
    @login_required
    def api_board_stats():
        scope = catalog_scope_flags()
        timezone_name = (request.args.get("timezone") or "").strip() or None
        latest_fetch_new_jobs = request.args.get("latest_fetch_new_jobs", type=int) or 0
        return jsonify(compute_user_board_stats(
            user_id=g.user_id,
            country_key=scope["country_key"],
            timezone_name=timezone_name,
            latest_fetch_new_jobs=latest_fetch_new_jobs,
        ))
