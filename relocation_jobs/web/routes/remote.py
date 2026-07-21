from __future__ import annotations

import math

from flask import g, jsonify, request

from relocation_jobs.core.auth import login_required
from relocation_jobs.core.paths import supported_countries
from relocation_jobs.catalog.locations import list_company_locations
from relocation_jobs.panel.stats import compute_user_board_stats, resolve_new_jobs_count
from relocation_jobs.remote.board import (
    DEFAULT_BOARD_PAGE_SIZE,
    MAX_BOARD_PAGE_SIZE,
    load_remote_board_page,
)
from relocation_jobs.remote.countries import list_remote_ats_types, list_remote_countries
from relocation_jobs.shared.board_contract import (
    CATALOG_KIND_REMOTE,
    board_page_payload,
    is_remote_country_key,
)
from relocation_jobs.web.query import catalog_scope_flags, query_flags


def _panel_flags() -> dict:
    flags = query_flags()
    return {
        "visa_only": False,
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


def _latest_fetch_new_jobs(
    file_meta: list[dict],
    *,
    user_id: int | None,
    country_key: str | None,
    timezone_name: str | None,
) -> int:
    return resolve_new_jobs_count(
        user_id=user_id,
        country_key=country_key,
        timezone_name=timezone_name,
        file_meta=file_meta,
    )


def register(app):
    @app.get("/api/remote/board")
    @login_required
    def api_remote_board():
        scope = catalog_scope_flags()
        country_key = scope["country_key"]
        if country_key and not is_remote_country_key(country_key):
            return jsonify({"error": f"Unknown remote board: {country_key}"}), 400
        timezone_name = (request.args.get("timezone") or "").strip() or None
        search = (request.args.get("q") or "").strip() or None
        page = max(request.args.get("page", 1, type=int) or 1, 1)
        page_size = request.args.get("page_size", DEFAULT_BOARD_PAGE_SIZE, type=int) or DEFAULT_BOARD_PAGE_SIZE
        page_size = max(1, min(page_size, MAX_BOARD_PAGE_SIZE))
        visible_offset = (page - 1) * page_size
        sort = (request.args.get("sort") or "newest").strip().lower()
        if sort not in ("newest", "name"):
            sort = "newest"

        companies, file_meta, fetch_problem_count, total_visible, has_more = load_remote_board_page(
            country_key,
            ats_type=scope["ats_type"],
            location=scope["location"],
            user_id=g.user_id,
            visible_offset=visible_offset,
            limit=page_size,
            search=search,
            panel_flags=_panel_flags(),
            count_total=(page == 1),
            sort=sort,
        )
        latest_fetch_new_jobs = _latest_fetch_new_jobs(
            file_meta,
            user_id=g.user_id,
            country_key=country_key,
            timezone_name=timezone_name,
        )
        total_pages = None
        if total_visible is not None:
            total_pages = max(1, math.ceil(total_visible / page_size))
        return jsonify(board_page_payload(
            companies=companies,
            meta={
                "country": request.args.get("country", "all"),
                "ats_type": scope["ats_type"],
                "location": scope["location"],
                "catalog_kind": CATALOG_KIND_REMOTE,
                "fetch_problem_total": fetch_problem_count,
                "latest_fetch_new_jobs": latest_fetch_new_jobs,
                "page": page,
                "page_size": page_size,
                "total_companies": total_visible,
                "total_pages": total_pages,
                "has_more": has_more,
                "sort": sort,
            },
            user_stats=compute_user_board_stats(
                user_id=g.user_id,
                country_key=country_key,
                timezone_name=timezone_name,
                latest_fetch_new_jobs=latest_fetch_new_jobs,
            ),
        ))

    @app.get("/api/remote/board/stats")
    @login_required
    def api_remote_board_stats():
        scope = catalog_scope_flags()
        country_key = scope["country_key"]
        if country_key and not is_remote_country_key(country_key):
            return jsonify({"error": f"Unknown remote board: {country_key}"}), 400
        timezone_name = (request.args.get("timezone") or "").strip() or None
        latest_fetch_new_jobs = request.args.get("latest_fetch_new_jobs", type=int) or 0
        return jsonify(compute_user_board_stats(
            user_id=g.user_id,
            country_key=country_key,
            timezone_name=timezone_name,
            latest_fetch_new_jobs=latest_fetch_new_jobs,
        ))

    @app.get("/api/remote/countries")
    @login_required
    def api_remote_countries():
        return jsonify(list_remote_countries())

    @app.get("/api/remote/ats-types")
    @login_required
    def api_remote_ats_types():
        return jsonify({"ats_types": list_remote_ats_types()})

    @app.get("/api/remote/locations")
    @login_required
    def api_remote_locations():
        country = request.args.get("country", "all")
        country_key = country if country != "all" else None
        if country_key and not is_remote_country_key(country_key):
            return jsonify({"error": f"Unknown remote board: {country}"}), 400
        if country_key and country_key not in supported_countries():
            return jsonify({"error": f"Unknown country: {country}"}), 400
        for_picker = request.args.get("picker", "").lower() in ("1", "true", "yes")
        if country_key:
            locations = list_company_locations(country_key, for_picker=for_picker)
        else:
            locations = []
            for key in sorted(supported_countries()):
                if is_remote_country_key(key):
                    locations.extend(list_company_locations(key, for_picker=for_picker))
        return jsonify({"locations": locations})
