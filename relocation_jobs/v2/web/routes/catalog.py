from __future__ import annotations

from flask import jsonify, request

from relocation_jobs.core.auth import login_required
from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.v2.catalog.repo import get_company
from relocation_jobs.v2.fetch.repo import list_attempts
from relocation_jobs.v2.fetch.types import AttemptStatus


def register(app):
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
        rows = list_attempts(
            country=country,
            company_name=company,
            status=status,
            limit=limit,
        )
        return jsonify({"attempts": [row.model_dump() for row in rows]})

    @app.get("/api/companies/<country>/<path:company_name>")
    @login_required
    def api_company_detail(country: str, company_name: str):
        country = country.strip().lower()
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        company = get_company(country, company_name)
        if company is None:
            return jsonify({"error": f"Company not found: {company_name}"}), 404
        return jsonify({"company": company})
