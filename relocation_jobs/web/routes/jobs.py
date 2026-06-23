"""Job tracking API routes."""

from __future__ import annotations

from flask import g, jsonify, request

from relocation_jobs.core.auth import login_required
from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.services.catalog_service import compute_stats, flatten_companies
from relocation_jobs.web import deps
from relocation_jobs.web.helpers import query_flags


def register(app):
    @app.get("/api/jobs")
    @login_required
    def api_jobs():
        flags = query_flags()
        companies, file_meta, fetch_problem_count = flatten_companies(
            flags["country_key"],
            visa_only=flags["visa_only"],
            hide_applied=flags["hide_applied"],
            hide_empty=flags["hide_empty"],
            not_applied_only=flags["not_applied_only"],
            hide_position_applied=flags["hide_position_applied"],
            hide_position_rejected=flags["hide_position_rejected"],
            position_applied_only=flags["position_applied_only"],
            position_rejected_only=flags["position_rejected_only"],
            position_looking_to_apply_only=flags["position_looking_to_apply_only"],
            fetch_ok_only=flags["fetch_ok_only"],
            fetch_problem_only=flags["fetch_problem_only"],
            location=flags["location"],
            city=flags["city"],
            ats_type=flags["ats_type"],
            user_id=g.user_id,
        )
        stats = compute_stats(
            companies,
            file_meta,
            fetch_problem_count=fetch_problem_count,
            user_id=g.user_id,
            country_key=flags["country_key"],
            timezone_name=flags["timezone_name"],
        )
        return jsonify({"companies": companies, "stats": stats})


    @app.patch("/api/jobs/applied")
    @app.post("/api/jobs/applied")
    @login_required
    def api_jobs_applied():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")
        applied = bool(body.get("applied", True))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        try:
            result = deps.set_job_applied(country, company, url, applied, user_id=g.user_id)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.patch("/api/jobs/rejected")
    @app.post("/api/jobs/rejected")
    @login_required
    def api_jobs_rejected():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")
        rejected = bool(body.get("rejected", True))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        try:
            result = deps.set_job_rejected(country, company, url, rejected, user_id=g.user_id)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.patch("/api/jobs/reapply")
    @app.post("/api/jobs/reapply")
    @login_required
    def api_jobs_reapply():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        try:
            result = deps.set_job_reapply(country, company, url, user_id=g.user_id)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.patch("/api/jobs/ats-score")
    @app.post("/api/jobs/ats-score")
    @login_required
    def api_jobs_ats_score():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        raw_score = body.get("ats_score")
        if raw_score is None or raw_score == "":
            ats_score = None
        else:
            try:
                ats_score = int(raw_score)
            except (TypeError, ValueError):
                return jsonify({"error": "ats_score must be an integer 0–100"}), 400
            if not 0 <= ats_score <= 100:
                return jsonify({"error": "ats_score must be between 0 and 100"}), 400

        try:
            result = deps.set_job_ats_score(country, company, url, ats_score, user_id=g.user_id)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.patch("/api/jobs/waiting-referral")
    @app.post("/api/jobs/waiting-referral")
    @login_required
    def api_jobs_waiting_referral():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")
        waiting_referral = bool(body.get("waiting_referral", True))
        linkedin_url = (body.get("linkedin_url") or body.get("referral_linkedin_url") or "").strip()

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        try:
            result = deps.set_job_waiting_referral(
                country,
                company,
                url,
                waiting_referral,
                user_id=g.user_id,
                linkedin_url=linkedin_url,
            )
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.post("/api/jobs/not-for-me")
    @login_required
    def api_jobs_not_for_me():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")
        not_for_me = bool(body.get("not_for_me", True))
        reason = (body.get("reason") or "").strip() or None

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        try:
            result = deps.set_job_not_for_me(
                country,
                company,
                url,
                user_id=g.user_id,
                not_for_me=not_for_me,
                reason=reason,
            )
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.patch("/api/jobs/looking-to-apply")
    @app.post("/api/jobs/looking-to-apply")
    @login_required
    def api_jobs_looking_to_apply():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")
        looking_to_apply = bool(body.get("looking_to_apply", True))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        try:
            result = deps.set_job_looking_to_apply(country, company, url, looking_to_apply, user_id=g.user_id)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.patch("/api/jobs/seen")
    @app.post("/api/jobs/seen")
    @login_required
    def api_jobs_seen():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "")
        company = body.get("company", "")
        url = body.get("url", "")
        seen = bool(body.get("seen", True))

        if not country or country == "all":
            return jsonify({"error": "country is required (not 'all')"}), 400
        if country not in SUPPORTED_COUNTRIES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if not company or not url:
            return jsonify({"error": "company and url are required"}), 400

        try:
            result = deps.set_job_seen(country, company, url, seen, user_id=g.user_id)
            return jsonify({"ok": True, **result})
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
