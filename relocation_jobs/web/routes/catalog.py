from __future__ import annotations

from flask import g, jsonify, request

from relocation_jobs.core.auth import admin_required, login_required
from relocation_jobs.core.ats_constants import DEFAULT_CONCURRENCY, HTTPX_AVAILABLE, MAX_CONCURRENCY
from relocation_jobs.core.location_tags import add_custom_city, add_custom_country, all_country_labels
from relocation_jobs.core.panel_flags import company_fetch_enabled, scrape_enabled
from relocation_jobs.core.paths import supported_countries
from relocation_jobs.catalog.locations import list_company_locations
from relocation_jobs.shared.board_contract import (
    AGGREGATOR_ATS_TYPES,
    CATALOG_KIND_RELOCATION,
    countries_for_kind,
    is_remote_country_key,
)
from relocation_jobs.web import deps


def register(app):
    @app.get("/api/config")
    @login_required
    def api_config():
        return jsonify({
            "default_concurrency": DEFAULT_CONCURRENCY,
            "max_concurrency": MAX_CONCURRENCY,
            "mode": "asyncio",
            "httpx_available": HTTPX_AVAILABLE,
            "scrape_enabled": scrape_enabled(),
            "company_fetch_enabled": company_fetch_enabled(),
            "description": (
                "Scraper uses an asyncio event loop with httpx for ATS API calls. "
                f"'--workers N' means {DEFAULT_CONCURRENCY} companies in flight by default."
            ),
        })

    @app.get("/api/countries")
    @login_required
    def api_countries():
        return jsonify(countries_for_kind(CATALOG_KIND_RELOCATION, all_country_labels()))

    @app.post("/api/countries")
    @login_required
    def api_countries_add():
        body = request.get_json(silent=True) or {}
        label = (body.get("label") or body.get("country") or body.get("name") or "").strip()
        if not label:
            return jsonify({"error": "Country name is required"}), 400
        try:
            country = add_custom_country(label)
            if is_remote_country_key(country.get("id")):
                return jsonify({"error": "Remote boards are managed separately"}), 400
            return jsonify({"ok": True, "country": country})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/countries/<country>")
    @app.post("/api/countries/remove")
    @admin_required
    def api_countries_remove(country: str | None = None):
        if country is None:
            body = request.get_json(silent=True) or {}
            country = (body.get("country") or "").strip().lower()
        else:
            country = country.strip().lower()
        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        try:
            result = deps.remove_country(country)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            message = str(exc)
            if message.startswith("Fetch is running"):
                return jsonify({"error": message}), 409
            return jsonify({"error": message}), 400

    @app.get("/api/ats-types")
    @login_required
    def api_ats_types():
        return jsonify({
            "ats_types": [
                row for row in deps.list_ats_types()
                if row.get("id") not in AGGREGATOR_ATS_TYPES
            ],
        })

    @app.get("/api/cities")
    @login_required
    def api_cities():
        country = request.args.get("country", "all")
        country_key = country if country != "all" else None
        if country != "all" and country not in supported_countries():
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if country_key and is_remote_country_key(country_key):
            return jsonify({"error": f"Unknown country: {country}"}), 400
        for_picker = request.args.get("picker", "").lower() in ("1", "true", "yes")
        if country_key:
            locations = list_company_locations(country_key, for_picker=for_picker)
        else:
            locations = [
                loc for loc in list_company_locations(None, for_picker=for_picker)
                if not is_remote_country_key(loc.get("country"))
            ]
        return jsonify({
            "cities": [loc["city"] for loc in locations],
            "locations": locations,
        })

    @app.get("/api/locations")
    @login_required
    def api_locations():
        country = request.args.get("country", "all")
        country_key = country if country != "all" else None
        if country != "all" and country not in supported_countries():
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if country_key and is_remote_country_key(country_key):
            return jsonify({"error": f"Unknown country: {country}"}), 400
        for_picker = request.args.get("picker", "").lower() in ("1", "true", "yes")
        if country_key:
            locations = list_company_locations(country_key, for_picker=for_picker)
        else:
            locations = [
                loc for loc in list_company_locations(None, for_picker=for_picker)
                if not is_remote_country_key(loc.get("country"))
            ]
        return jsonify({
            "locations": locations,
        })

    @app.post("/api/locations")
    @login_required
    def api_locations_add():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        city = (body.get("city") or "").strip()
        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in supported_countries():
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
