from __future__ import annotations

import os

from flask import jsonify, request

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.auth import admin_required
from relocation_jobs.db import list_users_with_stats
from relocation_jobs.admin import service as admin_service
from relocation_jobs.catalog.stats import get_catalog_overview
from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.fetch.runner import build_fetch_status


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


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
                admin_service.get_admin_dashboard(
                    fetch_state=build_fetch_status(),
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
                admin_service.get_admin_overview(fetch_state=build_fetch_status())
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
