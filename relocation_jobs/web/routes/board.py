from __future__ import annotations

from flask import g, jsonify, request

from relocation_jobs.core.auth import login_required
from relocation_jobs.panel.board import load_catalog_board
from relocation_jobs.panel.stats import compute_user_board_stats
from relocation_jobs.web.query import catalog_scope_flags


def register(app):
    @app.get("/api/board")
    @login_required
    def api_board():
        scope = catalog_scope_flags()
        companies, file_meta, fetch_problem_count = load_catalog_board(
            scope["country_key"],
            ats_type=scope["ats_type"],
            location=scope["location"],
            user_id=g.user_id,
        )
        latest_fetch_new_jobs = sum(int(row.get("last_fetch_new_jobs") or 0) for row in file_meta)
        return jsonify({
            "companies": companies,
            "meta": {
                "country": request.args.get("country", "all"),
                "ats_type": scope["ats_type"],
                "location": scope["location"],
                "fetch_problem_total": fetch_problem_count,
                "latest_fetch_new_jobs": latest_fetch_new_jobs,
            },
        })

    @app.get("/api/board/stats")
    @login_required
    def api_board_stats():
        scope = catalog_scope_flags()
        timezone_name = (request.args.get("timezone") or "").strip() or None
        _, file_meta, _ = load_catalog_board(
            scope["country_key"],
            ats_type=scope["ats_type"],
            location=scope["location"],
            user_id=g.user_id,
        )
        latest_fetch_new_jobs = sum(int(row.get("last_fetch_new_jobs") or 0) for row in file_meta)
        return jsonify(compute_user_board_stats(
            user_id=g.user_id,
            country_key=scope["country_key"],
            timezone_name=timezone_name,
            latest_fetch_new_jobs=latest_fetch_new_jobs,
        ))
