from __future__ import annotations

from flask import g, jsonify, request

from pydantic import ValidationError

from relocation_jobs.core.auth import login_required
from relocation_jobs.mcp import service as mcp_service
from relocation_jobs.mcp.types import ApplicationProfile


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
