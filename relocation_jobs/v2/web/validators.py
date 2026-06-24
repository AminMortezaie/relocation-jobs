from __future__ import annotations

from flask import jsonify

from relocation_jobs.core.paths import SUPPORTED_COUNTRIES


def job_mutation_error(body: dict) -> tuple | None:
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")
    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in SUPPORTED_COUNTRIES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400
    return None


def job_mutation_fields(body: dict) -> tuple[str, str, str]:
    return body.get("country", ""), body.get("company", ""), body.get("url", "")
