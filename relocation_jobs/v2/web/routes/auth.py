from __future__ import annotations

from flask import jsonify, request

from relocation_jobs.core.auth import (
    auth_status,
    authenticate,
    login_user,
    logout_user,
    register_user,
)


def register(app):
    @app.get("/api/auth/status")
    def api_auth_status():
        return jsonify(auth_status())

    @app.post("/api/auth/login")
    def api_auth_login():
        body = request.get_json(silent=True) or {}
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        user = authenticate(username, password)
        if not user:
            return jsonify({"error": "Invalid username or password"}), 401
        login_user(user["id"], user["username"])
        return jsonify({"ok": True, **auth_status()})

    @app.post("/api/auth/logout")
    def api_auth_logout():
        logout_user()
        return jsonify({"ok": True, "authenticated": False})

    @app.post("/api/auth/register")
    def api_auth_register():
        body = request.get_json(silent=True) or {}
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        try:
            user = register_user(username, password)
            login_user(user["id"], user["username"])
            return jsonify({"ok": True, **auth_status()})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
