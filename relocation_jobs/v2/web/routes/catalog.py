from __future__ import annotations

import os

from flask import g, jsonify, request

from relocation_jobs.core.auth import login_required
from relocation_jobs.core.ats_constants import DEFAULT_CONCURRENCY, HTTPX_AVAILABLE
from relocation_jobs.core.location_tags import COUNTRY_LABELS, add_custom_city
from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.v2.catalog.locations import list_company_locations
from relocation_jobs.v2.web import deps


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


def register(app):
    @app.get("/api/config")
    @login_required
    def api_config():
        return jsonify({
            "default_concurrency": DEFAULT_CONCURRENCY,
            "max_concurrency": 64,
            "mode": "asyncio",
            "httpx_available": HTTPX_AVAILABLE,
            "scrape_enabled": scrape_enabled(),
            "description": (
                "Scraper uses an asyncio event loop with httpx for ATS API calls. "
                f"'--workers N' means {DEFAULT_CONCURRENCY} companies in flight by default."
            ),
        })

    @app.get("/api/countries")
    @login_required
    def api_countries():
        return jsonify([
            {"id": "all", "label": "All countries"},
            *[{"id": k, "label": COUNTRY_LABELS[k]} for k in sorted(SUPPORTED_COUNTRIES)],
        ])

    @app.get("/api/ats-types")
    @login_required
    def api_ats_types():
        return jsonify({"ats_types": deps.list_ats_types()})

    @app.get("/api/cities")
    @login_required
    def api_cities():
        country = request.args.get("country", "all")
        country_key = country if country != "all" else None
        if country != "all" and country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        for_picker = request.args.get("picker", "").lower() in ("1", "true", "yes")
        locations = list_company_locations(country_key, for_picker=for_picker)
        return jsonify({
            "cities": [loc["city"] for loc in locations],
            "locations": locations,
        })

    @app.get("/api/locations")
    @login_required
    def api_locations():
        country = request.args.get("country", "all")
        country_key = country if country != "all" else None
        if country != "all" and country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        for_picker = request.args.get("picker", "").lower() in ("1", "true", "yes")
        return jsonify({
            "locations": list_company_locations(country_key, for_picker=for_picker),
        })

    @app.post("/api/locations")
    @login_required
    def api_locations_add():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        city = (body.get("city") or "").strip()
        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not city:
            return jsonify({"error": "city is required"}), 400
        try:
            location = add_custom_city(country, city)
            restored = deps.reconcile_wrong_location_hides(
                g.user_id,
                country_key=country,
                city_label=location["city"],
            )
            return jsonify({"ok": True, "location": location, "restored_jobs": restored})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
