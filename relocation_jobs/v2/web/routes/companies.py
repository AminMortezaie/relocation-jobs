from __future__ import annotations

import os

from flask import g, jsonify, request

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.auth import login_required
from relocation_jobs.core.location_tags import COUNTRY_LABELS
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, SUPPORTED_COUNTRIES
from relocation_jobs.v2.catalog.repo import get_company
from relocation_jobs.v2.fetch.runner import fetch_is_running, start_company_fetch
from relocation_jobs.v2.web import deps


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


def register(app):
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

    @app.patch("/api/companies/applied")
    @app.post("/api/companies/applied")
    @login_required
    def api_companies_applied():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        applied = bool(body.get("applied", body.get("company_applied", True)))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            result = deps.set_company_applied(country, company, applied, user_id=g.user_id)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.patch("/api/companies/awaiting-response")
    @app.post("/api/companies/awaiting-response")
    @login_required
    def api_companies_awaiting_response():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        awaiting = bool(body.get("awaiting_response", body.get("awaiting", True)))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            result = deps.set_company_awaiting_response(
                country, company, awaiting, user_id=g.user_id,
            )
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/companies")
    @login_required
    def api_companies_add():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        countries = body.get("countries")
        name = body.get("name", "")
        careers_url = body.get("careers_url", "")
        ats_hint = (body.get("ats") or body.get("ats_hint") or "").strip().lower()
        locations = body.get("locations")

        if not name.strip():
            return jsonify({"error": "Company name is required"}), 400
        if not careers_url.strip():
            return jsonify({"error": "Careers page URL is required"}), 400

        country_keys: list[str] | None = None
        if isinstance(countries, list) and countries:
            country_keys = [
                (item or "").strip().lower()
                for item in countries
                if (item or "").strip()
            ]
            for key in country_keys:
                if key not in SUPPORTED_COUNTRIES:
                    return jsonify({"error": f"Unknown country: {key}"}), 400
        else:
            country_hint = None if country in ("", "auto", "all") else country
            if country_hint and country_hint not in SUPPORTED_COUNTRIES:
                return jsonify({"error": f"Unknown country: {country}"}), 400
            if country_hint:
                country_keys = [country_hint]

        if locations is not None and not isinstance(locations, list):
            return jsonify({"error": "locations must be an array"}), 400

        valid_ats = {item["id"] for item in deps.list_ats_types()}
        if ats_hint and ats_hint not in ("auto", "") and ats_hint not in valid_ats:
            return jsonify({"error": f"Unknown ATS: {ats_hint}"}), 400
        ats_hint_arg = None if ats_hint in ("", "auto") else ats_hint

        try:
            result = deps.add_company(
                name,
                careers_url,
                country_keys[0] if country_keys else None,
                country_keys=country_keys,
                ats_hint=ats_hint_arg,
                locations=locations,
            )
            return jsonify({"ok": True, "company": result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 409
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.delete("/api/companies")
    @app.post("/api/companies/remove")
    @login_required
    def api_companies_remove():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
            result = deps.remove_company(country, company)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.patch("/api/companies/name")
    @app.post("/api/companies/name")
    @login_required
    def api_companies_rename():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()
        new_name = (body.get("new_name") or body.get("name") or "").strip()

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400
        if not new_name:
            return jsonify({"error": "new_name is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
            result = deps.rename_company(country, company, new_name)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 409 if "already exists" in str(e).lower() else 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.patch("/api/companies/careers")
    @app.post("/api/companies/careers")
    @login_required
    def api_companies_careers():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()
        careers_url = body.get("careers_url", "")
        redetect_ats = bool(body.get("redetect_ats", True))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400
        if not careers_url.strip():
            return jsonify({"error": "careers_url is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
            result = deps.update_company_careers(
                country, company, careers_url, redetect_ats=redetect_ats,
            )
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.patch("/api/companies/city")
    @app.post("/api/companies/city")
    @login_required
    def api_companies_city():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()
        cities = body.get("cities")
        locations = body.get("locations")
        if locations is None and cities is None:
            legacy_city = (body.get("city") or "").strip()
            cities = [legacy_city] if legacy_city else []
        elif locations is not None and not isinstance(locations, list):
            return jsonify({"error": "locations must be an array"}), 400
        elif cities is not None and not isinstance(cities, list):
            return jsonify({"error": "cities must be an array"}), 400

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
            result = deps.update_company_city(
                country,
                company,
                cities=cities,
                locations=locations,
            )
            restored = deps.reconcile_wrong_location_hides(g.user_id, country_key=country)
            return jsonify({"ok": True, **result, "restored_jobs": restored})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.patch("/api/companies/fetch-problem")
    @app.post("/api/companies/fetch-problem")
    @login_required
    def api_companies_fetch_problem():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()
        fetch_problem = bool(body.get("fetch_problem", True))
        mark_fetch_ok = bool(body.get("mark_fetch_ok", False))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
            result = deps.set_company_fetch_problem(
                country, company, fetch_problem, mark_fetch_ok=mark_fetch_ok,
            )
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/companies/fetch-ok")
    @login_required
    def api_companies_fetch_ok():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
            result = deps.set_company_fetch_ok(country, company)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/companies/jobs/manual-add")
    @login_required
    def api_companies_jobs_manual_add():
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()
        jobs = body.get("jobs") or []

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400
        if not isinstance(jobs, list) or not jobs:
            return jsonify({"error": "jobs must be a non-empty list"}), 400

        try:
            company = deps.resolve_company_name(country, company)
            result = deps.add_manual_jobs(country, company, jobs)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/companies/fetch")
    @login_required
    def api_companies_fetch():
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
        country = (body.get("country") or "").strip().lower()
        company = (body.get("company") or "").strip()

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company:
            return jsonify({"error": "company is required"}), 400

        try:
            company = deps.resolve_company_name(country, company)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404

        if fetch_is_running():
            return jsonify({"error": "A fetch is already running"}), 409

        try:
            deps.touch_company_fetch_time(country, company)
        except (LookupError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

        try:
            run_id = start_company_fetch(
                user_id=g.user_id,
                country_key=country,
                company_name=company,
            )
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409

        return jsonify({
            "ok": True,
            "run_id": run_id,
            "country": country,
            "company": company,
            "file": COUNTRY_ARCHIVE_FILENAMES.get(country, ""),
            "message": f"Fetching jobs for {company} ({COUNTRY_LABELS.get(country, country)})",
        })
