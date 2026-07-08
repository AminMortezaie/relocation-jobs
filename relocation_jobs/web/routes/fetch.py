from __future__ import annotations

import os

from flask import g, jsonify, request

from relocation_jobs.core.ats_constants import DEFAULT_CONCURRENCY, HTTPX_AVAILABLE, MAX_CONCURRENCY
from relocation_jobs.core.auth import admin_required, login_required
from relocation_jobs.core.location_tags import country_label
from relocation_jobs.core.paths import country_archive_filename, supported_countries
from relocation_jobs.users.repo import is_user_admin
from relocation_jobs.web import deps
from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.fetch import state as fetch_state
from relocation_jobs.fetch.runner import (
    start_country_fetch,
)
from relocation_jobs.fetch.types import AttemptStatus


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


def register(app):
    @app.get("/api/fetch/status")
    @login_required
    def api_fetch_status():
        return jsonify(fetch_state.build_fetch_status())

    @app.post("/api/fetch/cancel")
    @login_required
    def api_fetch_cancel():
        status = fetch_state.build_fetch_status()
        if not status.get("running"):
            return jsonify({"error": "No fetch is running"}), 400
        if not status.get("company") and not is_user_admin(g.user_id):
            return jsonify({"error": "Admin access required"}), 403
        ok, err = fetch_state.request_fetch_cancel()
        if not ok:
            return jsonify({"error": err or "No fetch is running"}), 400
        return jsonify({"ok": True})

    @app.get("/api/fetch/history")
    @admin_required
    def api_fetch_history():
        country = (request.args.get("country") or "").strip().lower() or None
        if country and country not in supported_countries():
            return jsonify({"error": f"Unknown country: {country}"}), 400
        try:
            limit = int(request.args.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20
        return jsonify({
            "runs": fetch_repo.list_user_fetch_runs(g.user_id, country=country, limit=limit),
        })

    @app.post("/api/fetch")
    @admin_required
    def api_fetch_country():
        if not scrape_enabled():
            return jsonify({
                "error": (
                    "Scraping is disabled on this host. "
                    "Run scrapes locally, then sync catalog to Postgres."
                ),
            }), 503

        if not HTTPX_AVAILABLE:
            return jsonify({
                "error": "httpx is not installed. Run: pip install httpx",
            }), 503

        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "netherlands").strip().lower()
        skip_filled = bool(body.get("skip_filled", False))
        try:
            concurrency = int(body.get("concurrency", body.get("workers", DEFAULT_CONCURRENCY)))
        except (TypeError, ValueError):
            concurrency = 1
        ats_raw = (body.get("ats_type") or body.get("ats") or "").strip()
        ats_type = ats_raw if ats_raw and ats_raw != "all" else None

        if country == "all":
            return jsonify({"error": "Select a single country to fetch (not 'all')"}), 400
        if country not in supported_countries():
            return jsonify({"error": f"Unknown country: {country}"}), 400

        valid_ats = {item["id"] for item in deps.list_ats_types()} | {"generic"}
        if ats_type and ats_type not in valid_ats:
            return jsonify({"error": f"Unknown ATS type: {ats_type}"}), 400

        if not fetch_state.guard_fetch_start():
            return jsonify({"error": "A fetch is already running"}), 409

        try:
            run_id = start_country_fetch(
                user_id=g.user_id,
                country_key=country,
                skip_filled=skip_filled,
                ats_type=ats_type,
                concurrency=concurrency,
            )
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 400

        workers = max(1, min(concurrency, MAX_CONCURRENCY))
        return jsonify({
            "ok": True,
            "run_id": run_id,
            "country": country,
            "ats_type": ats_type,
            "file": country_archive_filename(country),
            "concurrency": workers,
            "message": (
                f"Started scraping {country_label(country)} "
                f"({workers} concurrent)"
            ),
        })

    @app.get("/api/fetch/attempts")
    @login_required
    def api_fetch_attempts():
        country = (request.args.get("country") or "").strip().lower() or None
        company = (request.args.get("company") or "").strip() or None
        if country and country not in supported_countries():
            return jsonify({"error": f"Unknown country: {country}"}), 400
        try:
            limit = int(request.args.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        status_raw = (request.args.get("status") or "").strip().lower()
        status = AttemptStatus(status_raw) if status_raw else None
        rows = fetch_repo.list_attempts(
            country=country,
            company_name=company,
            status=status,
            limit=limit,
        )
        return jsonify({"attempts": [row.model_dump() for row in rows]})
