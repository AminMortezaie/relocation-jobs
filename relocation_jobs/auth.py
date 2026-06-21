"""Session-based authentication for the job panel."""

from __future__ import annotations

import os
import secrets
from functools import wraps

from flask import g, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from relocation_jobs.db import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    init_db,
    is_user_admin,
    migrate_tracking_from_json,
    tracking_is_empty,
    user_count,
)


def secret_key() -> str:
    key = os.environ.get("PANEL_SECRET_KEY", "").strip()
    if key:
        return key
    return secrets.token_hex(32)


def allow_register() -> bool:
    return os.environ.get("PANEL_ALLOW_REGISTER", "").lower() in ("1", "true", "yes")


def login_user(user_id: int, username: str) -> None:
    session.clear()
    session["user_id"] = user_id
    session["username"] = username
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_user_id() -> int | None:
    uid = session.get("user_id")
    return int(uid) if uid is not None else None


def current_username() -> str | None:
    return session.get("username")


def auth_status() -> dict:
    uid = current_user_id()
    if not uid:
        return {"authenticated": False, "allow_register": allow_register()}
    user = get_user_by_id(uid)
    if not user:
        logout_user()
        return {"authenticated": False, "allow_register": allow_register()}
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "is_admin": is_user_admin(user["id"]),
        },
        "allow_register": allow_register(),
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        uid = current_user_id()
        if not uid or not get_user_by_id(uid):
            logout_user()
            return jsonify({"error": "Authentication required"}), 401
        g.user_id = uid
        g.username = current_username()
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not is_user_admin(g.user_id):
            return jsonify({"error": "Admin access required"}), 403
        return view(*args, **kwargs)

    return wrapped


def authenticate(username: str, password: str) -> dict | None:
    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return None
    return {"id": user["id"], "username": user["username"]}


def register_user(username: str, password: str) -> dict:
    username = username.strip()
    if len(username) < 2:
        raise ValueError("Username must be at least 2 characters")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if get_user_by_username(username):
        raise ValueError("Username already taken")
    if not allow_register() and user_count() > 0:
        raise ValueError("Registration is disabled")
    password_hash = generate_password_hash(password)
    return create_user(username, password_hash)


def bootstrap_admin() -> dict | None:
    """
    Create the first admin user from env and migrate JSON tracking into DB.
    Returns the created user dict, or None if users already exist.
    """
    if user_count() > 0:
        return None

    username = os.environ.get("PANEL_ADMIN_USER", "admin").strip() or "admin"
    password = os.environ.get("PANEL_ADMIN_PASSWORD", "").strip()
    if not password:
        password = secrets.token_urlsafe(12)
        print(
            f"Panel: created admin user '{username}' with generated password: {password}\n"
            "Set PANEL_ADMIN_USER and PANEL_ADMIN_PASSWORD to control this on first run."
        )

    user = create_user(username, generate_password_hash(password), is_admin=True)
    if tracking_is_empty():
        n = migrate_tracking_from_json(user["id"])
        if n:
            print(f"Panel: migrated {n} tracking row(s) from JSON into the database.")
    return user


def init_auth(app) -> None:
    app.secret_key = secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    init_db()
    bootstrap_admin()
