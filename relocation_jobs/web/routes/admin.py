"""Admin API routes."""

from __future__ import annotations

from flask import jsonify, request

from relocation_jobs.core.auth import admin_required
from relocation_jobs.web import deps
from relocation_jobs.db import list_all_fetch_runs, list_users_with_stats
from relocation_jobs.services.admin_service import (
    get_admin_dashboard,
    get_admin_overview,
    get_catalog_overview,
    get_system_config,
)
from relocation_jobs.web.helpers import admin_fetch_snapshot, scrape_enabled


def register(app):
    @app.get("/api/admin/dashboard")
    @admin_required
    def api_admin_dashboard():
        try:
            limit = 50
            raw_limit = request.args.get("limit")
            if raw_limit is not None:
                try:
                    limit = int(raw_limit)
                except ValueError:
                    limit = 50
            return jsonify(
                get_admin_dashboard(
                    fetch_state=admin_fetch_snapshot(),
                    scrape_enabled=scrape_enabled(),
                    httpx_available=deps.HTTPX_AVAILABLE,
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
            return jsonify(get_admin_overview(fetch_state=admin_fetch_snapshot()))
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
            return jsonify(
                {"runs": list_all_fetch_runs(country=country, limit=limit)}
            )
        except Exception as exc:
            app.logger.exception("admin fetch-runs failed")
            return jsonify({"error": str(exc)}), 500


    @app.get("/api/admin/config")
    @admin_required
    def api_admin_config():
        try:
            return jsonify(
                get_system_config(
                    scrape_enabled=scrape_enabled(),
                    httpx_available=deps.HTTPX_AVAILABLE,
                )
            )
        except Exception as exc:
            app.logger.exception("admin config failed")
            return jsonify({"error": str(exc)}), 500
