from __future__ import annotations

import os

from flask import g, jsonify, request

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.auth import admin_required
from relocation_jobs.users.repo import list_users_with_stats
from relocation_jobs.admin import service as admin_service
from relocation_jobs.catalog.repo import get_catalog_overview
from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.fetch import state as fetch_state
from relocation_jobs.web.query import catalog_scope_flags


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


def register(app):
    @app.get("/api/admin/dashboard")
    @admin_required
    def api_admin_dashboard():
        try:
            limit = 15
            raw_limit = request.args.get("limit")
            if raw_limit is not None:
                try:
                    limit = int(raw_limit)
                except ValueError:
                    limit = 15
            timezone_name = (request.args.get("timezone") or "").strip() or None
            return jsonify(
                admin_service.get_admin_dashboard(
                    fetch_state=fetch_state.build_fetch_status(),
                    scrape_enabled=scrape_enabled(),
                    httpx_available=HTTPX_AVAILABLE,
                    fetch_runs_limit=limit,
                )
            )
        except Exception as exc:
            app.logger.exception("admin dashboard failed")
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/admin/overview")
    @admin_required
    def api_admin_overview():
        try:
            return jsonify(
                admin_service.get_admin_overview(fetch_state=fetch_state.build_fetch_status())
            )
        except Exception as exc:
            app.logger.exception("admin overview failed")
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/admin/catalog")
    @admin_required
    def api_admin_catalog():
        try:
            return jsonify(get_catalog_overview())
        except Exception as exc:
            app.logger.exception("admin catalog failed")
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/admin/users")
    @admin_required
    def api_admin_users():
        try:
            return jsonify({"users": list_users_with_stats()})
        except Exception as exc:
            app.logger.exception("admin users failed")
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/admin/fetch-runs")
    @admin_required
    def api_admin_fetch_runs():
        country = (request.args.get("country") or "").strip() or None
        try:
            limit = int(request.args.get("limit", "50"))
        except ValueError:
            limit = 50
        try:
            return jsonify({
                "runs": fetch_repo.list_all_fetch_runs(country=country, limit=limit),
            })
        except Exception as exc:
            app.logger.exception("admin fetch-runs failed")
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/admin/panel-stats")
    @admin_required
    def api_admin_panel_stats():
        try:
            scope = catalog_scope_flags()
            timezone_name = (request.args.get("timezone") or "").strip() or None
            return jsonify(admin_service.compute_admin_panel_stats(
                user_id=g.user_id,
                country_key=scope["country_key"],
                location=scope["location"],
                ats_type=scope["ats_type"],
                timezone_name=timezone_name,
            ))
        except Exception as exc:
            app.logger.exception("admin panel-stats failed")
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/admin/recent-jobs")
    @admin_required
    def api_admin_recent_jobs():
        try:
            limit = int(request.args.get("limit", "30"))
        except ValueError:
            limit = 30
        try:
            timezone_name = (request.args.get("timezone") or "").strip() or None
            return jsonify({
                "jobs": admin_service.get_recently_fetched_jobs(
                    limit=limit,
                    timezone_name=timezone_name,
                ),
            })
        except Exception as exc:
            app.logger.exception("admin recent-jobs failed")
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/admin/config")
    @admin_required
    def api_admin_config():
        try:
            return jsonify(
                admin_service.get_system_config(
                    scrape_enabled=scrape_enabled(),
                    httpx_available=HTTPX_AVAILABLE,
                )
            )
        except Exception as exc:
            app.logger.exception("admin config failed")
            return jsonify({"error": str(exc)}), 500
