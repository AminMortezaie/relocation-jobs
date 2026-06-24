from __future__ import annotations

import os

from flask import g, jsonify, request

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.auth import admin_required, login_required
from relocation_jobs.core.location_tags import COUNTRY_LABELS
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, SUPPORTED_COUNTRIES
from relocation_jobs.db import is_user_admin
from relocation_jobs.v2.web import deps
from relocation_jobs.v2.fetch import repo as fetch_repo
from relocation_jobs.v2.fetch.runner import (
    build_fetch_status,
    fetch_is_running,
    request_fetch_cancel,
    start_country_fetch,
)
from relocation_jobs.v2.fetch.types import AttemptStatus


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


def register(app):
    @app.get("/api/fetch/status")
    @login_required
    def api_fetch_status():
        return jsonify(build_fetch_status())

    @app.post("/api/fetch/cancel")
    @login_required
    def api_fetch_cancel():
        status = build_fetch_status()
        if not status.get("running"):
            return jsonify({"error": "No fetch is running"}), 400
        if not status.get("company") and not is_user_admin(g.user_id):
            return jsonify({"error": "Admin access required"}), 403
        ok, err = request_fetch_cancel()
        if not ok:
            return jsonify({"error": err or "No fetch is running"}), 400
        return jsonify({"ok": True})

    @app.get("/api/fetch/history")
    @admin_required
    def api_fetch_history():
        country = (request.args.get("country") or "").strip().lower() or None
        if country and country not in SUPPORTED_COUNTRIES:
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
            concurrency = int(body.get("concurrency", body.get("workers", 1)))
        except (TypeError, ValueError):
            concurrency = 1
        ats_raw = (body.get("ats_type") or body.get("ats") or "").strip()
        ats_type = ats_raw if ats_raw and ats_raw != "all" else None

        if country == "all":
            return jsonify({"error": "Select a single country to fetch (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400

        valid_ats = {item["id"] for item in deps.list_ats_types()} | {"generic"}
        if ats_type and ats_type not in valid_ats:
            return jsonify({"error": f"Unknown ATS type: {ats_type}"}), 400

        if fetch_is_running():
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

        workers = max(1, min(concurrency, 64))
        return jsonify({
            "ok": True,
            "run_id": run_id,
            "country": country,
            "ats_type": ats_type,
            "file": COUNTRY_ARCHIVE_FILENAMES[country],
            "concurrency": workers,
            "message": (
                f"Started scraping {COUNTRY_LABELS.get(country, country)} "
                f"({workers} concurrent)"
            ),
        })

    @app.get("/api/fetch/attempts")
    @login_required
    def api_fetch_attempts():
        country = (request.args.get("country") or "").strip().lower() or None
        company = (request.args.get("company") or "").strip() or None
        if country and country not in SUPPORTED_COUNTRIES:
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
