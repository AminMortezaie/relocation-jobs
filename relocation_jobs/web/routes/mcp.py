from __future__ import annotations

import os
from urllib.parse import quote

from flask import Response, g, jsonify, request

from pydantic import ValidationError

from relocation_jobs.core.auth import login_required
from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.paths import supported_countries
from relocation_jobs.mcp import service as mcp_service
from relocation_jobs.mcp.types import ApplicationProfile


def _scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


def register(app):
    @app.get("/api/mcp/profile")
    @login_required
    def api_mcp_profile_get():
        profile = mcp_service.get_application_profile(user_id=g.user_id)
        return jsonify({"profile": profile.model_dump()})

    @app.put("/api/mcp/profile")
    @login_required
    def api_mcp_profile_put():
        body = request.get_json(silent=True) or {}
        try:
            profile = ApplicationProfile(**body)
        except ValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        saved = mcp_service.save_application_profile(profile, user_id=g.user_id)
        return jsonify({"ok": True, **saved, "profile": profile.model_dump()})

    @app.get("/api/mcp/master-resumes")
    @login_required
    def api_mcp_master_resumes_list():
        items = mcp_service.list_master_resumes(user_id=g.user_id)
        return jsonify({"items": [item.model_dump() for item in items]})

    @app.get("/api/mcp/master-resumes/<slug>")
    @login_required
    def api_mcp_master_resume_get(slug):
        try:
            detail = mcp_service.get_master_resume_detail(slug, user_id=g.user_id)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(detail)

    @app.put("/api/mcp/master-resumes/<slug>")
    @login_required
    def api_mcp_master_resume_put(slug):
        body = request.get_json(silent=True) or {}
        content = body.get("content")
        if content is None:
            return jsonify({"error": "content is required"}), 400
        label = (body.get("label") or "").strip()
        try:
            saved = mcp_service.save_master_resume(
                slug,
                str(content),
                label=label,
                user_id=g.user_id,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, **saved})

    @app.get("/api/mcp/master-resumes/<slug>/pdf")
    @login_required
    def api_mcp_master_resume_pdf(slug):
        try:
            pdf_bytes, filename = mcp_service.read_master_pdf_download(
                slug,
                user_id=g.user_id,
            )
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        quoted = quote(filename)
        download = request.args.get("download", "").strip().lower() in ("1", "true", "yes")
        disposition = "attachment" if download else "inline"
        headers = {
            "Content-Disposition": (
                f'{disposition}; filename="{filename}"; filename*=UTF-8\'\'{quoted}'
            ),
        }
        return Response(pdf_bytes, mimetype="application/pdf", headers=headers)

    @app.post("/api/mcp/master-resumes/<slug>/render")
    @login_required
    def api_mcp_master_resume_render(slug):
        try:
            result = mcp_service.render_master_pdf(slug, user_id=g.user_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not result.ok:
            return jsonify({"ok": False, "error": result.log, **result.model_dump()}), 400
        return jsonify({"ok": True, **result.model_dump()})

    @app.get("/api/mcp/companies/<country>/<path:company>/applications")
    @login_required
    def api_mcp_company_applications(country: str, company: str):
        country_key = country.strip().lower()
        if country_key not in supported_countries():
            return jsonify({"error": f"Unknown country: {country}"}), 400
        try:
            payload = mcp_service.list_company_applications(
                country_key,
                company,
                user_id=g.user_id,
            )
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(payload.model_dump())

    @app.get("/api/mcp/positions/<path:idempotency_key>/description")
    @login_required
    def api_mcp_position_description(idempotency_key: str):
        try:
            detail = mcp_service.get_position_description(idempotency_key)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(detail.model_dump())

    @app.post("/api/mcp/positions/<path:idempotency_key>/fetch-description")
    @login_required
    def api_mcp_position_fetch_description(idempotency_key: str):
        if not _scrape_enabled():
            return jsonify({
                "error": (
                    "Scraping is disabled on this host. "
                    "Run scrapes locally, then sync catalog to Postgres."
                ),
            }), 503
        if not HTTPX_AVAILABLE:
            return jsonify({"error": "httpx is not installed. Run: pip install httpx"}), 503
        try:
            detail = mcp_service.fetch_and_store_position_description(idempotency_key)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(detail.model_dump())

    @app.get("/api/mcp/applications/<path:idempotency_key>")
    @login_required
    def api_mcp_application_detail(idempotency_key: str):
        try:
            detail = mcp_service.get_application_detail(idempotency_key, user_id=g.user_id)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(detail.model_dump())

    @app.get("/api/mcp/applications/<path:idempotency_key>/tex")
    @login_required
    def api_mcp_application_tex(idempotency_key: str):
        try:
            detail = mcp_service.read_application_tex(idempotency_key, user_id=g.user_id)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(detail.model_dump())

    @app.put("/api/mcp/applications/<path:idempotency_key>/tex")
    @login_required
    def api_mcp_application_tex_put(idempotency_key: str):
        body = request.get_json(silent=True) or {}
        content = body.get("content")
        if content is None:
            return jsonify({"error": "content is required"}), 400
        try:
            saved = mcp_service.save_application_tex(
                idempotency_key,
                str(content),
                user_id=g.user_id,
            )
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(saved)

    @app.get("/api/mcp/applications/<path:idempotency_key>/pdf")
    @login_required
    def api_mcp_application_pdf(idempotency_key: str):
        try:
            pdf_bytes, filename = mcp_service.read_application_pdf_download(
                idempotency_key,
                user_id=g.user_id,
            )
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        quoted = quote(filename)
        download = request.args.get("download", "").strip().lower() in ("1", "true", "yes")
        disposition = "attachment" if download else "inline"
        headers = {
            "Content-Disposition": (
                f'{disposition}; filename="{filename}"; filename*=UTF-8\'\'{quoted}'
            ),
        }
        return Response(pdf_bytes, mimetype="application/pdf", headers=headers)

    @app.post("/api/mcp/applications/<path:idempotency_key>/render")
    @login_required
    def api_mcp_application_render(idempotency_key: str):
        result = mcp_service.render_application_pdf(idempotency_key, user_id=g.user_id)
        if not result.ok:
            return jsonify({"ok": False, "error": result.log, **result.model_dump()}), 400
        return jsonify({"ok": True, **result.model_dump()})
