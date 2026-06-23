"""Scrape fetch API routes."""

from __future__ import annotations

from flask import g, jsonify, request
from relocation_jobs.core.auth import admin_required, login_required
from relocation_jobs.web import deps
from relocation_jobs.core.location_tags import COUNTRY_LABELS
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, SUPPORTED_COUNTRIES
from relocation_jobs.services.catalog_service import list_ats_types
from relocation_jobs.db import is_user_admin, list_fetch_runs
from relocation_jobs.web.helpers import scrape_enabled
from relocation_jobs.web import scrape_runner
from relocation_jobs.web.fetch_state import _fetch_lock, _fetch_state


def register(app):
    @app.get("/api/fetch/status")
    @login_required
    def api_fetch_status():
        scrape_runner._reap_zombie_fetch()
        with _fetch_lock:
            return jsonify({
                "running": _fetch_state["running"],
                "country": _fetch_state["country"],
                "company": _fetch_state.get("company"),
                "ats_type": _fetch_state.get("ats_type"),
                "file": _fetch_state["file"],
                "started_at": _fetch_state["started_at"],
                "finished_at": _fetch_state["finished_at"],
                "exit_code": _fetch_state["exit_code"],
                "concurrency": _fetch_state.get("concurrency"),
                "result_line": _fetch_state.get("result_line"),
                "cancel_requested": _fetch_state.get("cancel_requested", False),
                "cancelled": _fetch_state.get("cancelled", False),
                "progress": dict(_fetch_state.get("progress") or {}),
                "activity": dict(_fetch_state.get("activity") or {}),
                "activity_log": list(_fetch_state.get("activity_log") or []),
                "log": list(_fetch_state["log"]),
                "review_jobs": _fetch_state.get("review_jobs"),
                "new_jobs_total": int(_fetch_state.get("new_jobs_total") or 0),
                "last_fetch_run": _fetch_state.get("last_fetch_run"),
            })


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
            "runs": list_fetch_runs(g.user_id, country=country, limit=limit),
        })


    @app.post("/api/fetch/cancel")
    @login_required
    def api_fetch_cancel():
        proc = None
        with _fetch_lock:
            if not _fetch_state["running"]:
                return jsonify({"error": "No fetch is running"}), 400
            if not _fetch_state.get("company") and not is_user_admin(g.user_id):
                return jsonify({"error": "Admin access required"}), 403
            _fetch_state["cancel_requested"] = True
            proc = _fetch_state.get("process")
        scrape_runner._terminate_scrape_process(proc)
        return jsonify({"ok": True})


    @app.post("/api/companies/fetch")
    @login_required
    def api_companies_fetch():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = (body.get("company") or "").strip()

        if not scrape_enabled():
            return jsonify({
                "error": "Scraping is disabled on this host. Run scrapes locally, then git push the JSON files.",
            }), 503

        if not deps.HTTPX_AVAILABLE:
            return jsonify({
                "error": "httpx is not installed. Run: pip install httpx",
            }), 503

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
        except LookupError as e:
            return jsonify({"error": str(e)}), 404

        with _fetch_lock:
            scrape_runner._reap_zombie_fetch()
            if _fetch_state["running"]:
                return jsonify({"error": "A fetch is already running"}), 409

            scrape_runner._reset_fetch_run_state(
                country=country,
                company=company,
                file_name=COUNTRY_ARCHIVE_FILENAMES[country],
                concurrency=1,
                user_id=g.user_id,
            )

        try:
            deps.touch_company_fetch_time(country, company)
        except (LookupError, ValueError) as e:
            return jsonify({"error": str(e)}), 404

        scrape_runner._start_scrape_thread(country, skip_filled=False, concurrency=1, company=company)

        return jsonify({
            "ok": True,
            "country": country,
            "company": company,
            "file": COUNTRY_ARCHIVE_FILENAMES[country],
            "message": f"Fetching jobs for {company} ({COUNTRY_LABELS[country]})",
        })


    @app.post("/api/fetch")
    @admin_required
    def api_fetch():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "netherlands")
        skip_filled = bool(body.get("skip_filled", False))
        concurrency = int(body.get("concurrency", body.get("workers", deps.DEFAULT_CONCURRENCY)))
        ats_raw = (body.get("ats_type") or body.get("ats") or "").strip()
        ats_type = ats_raw if ats_raw and ats_raw != "all" else None

        if not scrape_enabled():
            return jsonify({
                "error": "Scraping is disabled on this host. Run scrapes locally, then git push the JSON files.",
            }), 503

        if not deps.HTTPX_AVAILABLE:
            return jsonify({
                "error": "httpx is not installed. Run: pip install httpx",
            }), 503

        if country == "all":
            return jsonify({"error": "Select a single country to fetch (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400

        valid_ats = {item["id"] for item in list_ats_types()} | {"generic"}
        if ats_type and ats_type not in valid_ats:
            return jsonify({"error": f"Unknown ATS type: {ats_type}"}), 400

        with _fetch_lock:
            scrape_runner._reap_zombie_fetch()
            if _fetch_state["running"]:
                return jsonify({"error": "A fetch is already running"}), 409

            workers = max(1, min(concurrency, 64))
            scrape_runner._reset_fetch_run_state(
                country=country,
                company=None,
                file_name=COUNTRY_ARCHIVE_FILENAMES[country],
                concurrency=workers,
                user_id=g.user_id,
                ats_type=ats_type,
            )

        scrape_runner._start_scrape_thread(country, skip_filled, workers, ats_type=ats_type)

        ats_label = ""
        if ats_type:
            labels = {item["id"]: item["label"] for item in list_ats_types()}
            ats_label = labels.get(ats_type, ats_type.replace("_", " ").title())
        scope = f"{ats_label} companies in " if ats_type else ""
        return jsonify({
            "ok": True,
            "country": country,
            "ats_type": ats_type,
            "file": COUNTRY_ARCHIVE_FILENAMES[country],
            "concurrency": workers,
            "message": (
                f"Started scraping {scope}{COUNTRY_LABELS[country]} "
                f"({workers} concurrent, asyncio)"
            ),
        })
