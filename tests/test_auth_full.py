"""Auth module: register, bootstrap, login_required, session helpers."""

from __future__ import annotations

import json

import pytest
from flask import Flask, g, jsonify, session
from werkzeug.security import generate_password_hash

from relocation_jobs.core.auth import (
    allow_register,
    auth_status,
    authenticate,
    bootstrap_admin,
    current_user_id,
    current_username,
    init_auth,
    login_required,
    login_user,
    logout_user,
    register_user,
    secret_key,
)
from relocation_jobs.db import create_user, get_user_by_username, user_count


@pytest.fixture
def auth_app(db, monkeypatch):
    monkeypatch.setenv("PANEL_SECRET_KEY", "test-secret-fixed")
    monkeypatch.setenv("PANEL_ALLOW_REGISTER", "1")
    app = Flask(__name__)
    init_auth(app)
    app.config["TESTING"] = True
    return app


def test_allow_register(monkeypatch):
    monkeypatch.delenv("PANEL_ALLOW_REGISTER", raising=False)
    assert allow_register() is False
    monkeypatch.setenv("PANEL_ALLOW_REGISTER", "true")
    assert allow_register() is True
    monkeypatch.setenv("PANEL_ALLOW_REGISTER", "yes")
    assert allow_register() is True


def test_secret_key_from_env(monkeypatch):
    monkeypatch.setenv("PANEL_SECRET_KEY", "env-key")
    assert secret_key() == "env-key"


def test_secret_key_generated_when_missing(monkeypatch):
    monkeypatch.delenv("PANEL_SECRET_KEY", raising=False)
    key = secret_key()
    assert len(key) == 64


@pytest.mark.integration
def test_register_user_success(db):
    user = register_user("newbie", "longpassword")
    assert user["username"] == "newbie"
    assert get_user_by_username("newbie") is not None


@pytest.mark.integration
def test_register_user_validation(db):
    with pytest.raises(ValueError, match="at least 2"):
        register_user("a", "longpassword")
    with pytest.raises(ValueError, match="at least 8"):
        register_user("ab", "short")
    register_user("first", "longpass1")
    with pytest.raises(ValueError, match="already taken"):
        register_user("first", "longpass2")


@pytest.mark.integration
def test_register_disabled_when_users_exist(db, monkeypatch):
    create_user("existing", generate_password_hash("longpass1"))
    monkeypatch.delenv("PANEL_ALLOW_REGISTER", raising=False)
    with pytest.raises(ValueError, match="disabled"):
        register_user("another", "longpass2")


@pytest.mark.integration
def test_authenticate(db):
    create_user("authuser", generate_password_hash("correcthorse"))
    assert authenticate("authuser", "correcthorse")["username"] == "authuser"
    assert authenticate("authuser", "wrong") is None
    assert authenticate("missing", "x") is None


@pytest.mark.integration
def test_bootstrap_admin_creates_user(db, monkeypatch):
    monkeypatch.setenv("PANEL_ADMIN_USER", "bootstrap")
    monkeypatch.setenv("PANEL_ADMIN_PASSWORD", "bootstrap-pass-12")
    user = bootstrap_admin()
    assert user is not None
    assert user["username"] == "bootstrap"
    assert bootstrap_admin() is None


@pytest.mark.integration
def test_bootstrap_admin_migrates_tracking(db, monkeypatch, sample_country_data, capsys):
    monkeypatch.setenv("PANEL_ADMIN_USER", "admin2")
    monkeypatch.setenv("PANEL_ADMIN_PASSWORD", "admin2-pass-12")

    enriched = json.loads(json.dumps(sample_country_data))
    job = enriched["companies"][0]["matching_jobs"][0]
    job["applied"] = True
    job["applied_date"] = "2025-06-01"

    monkeypatch.setattr(
        "relocation_jobs.catalog_db.load_country",
        lambda key: enriched if key == "uk" else None,
    )

    user = bootstrap_admin()
    assert user is not None
    assert "migrated" in capsys.readouterr().out


@pytest.mark.integration
def test_bootstrap_admin_generated_password(db, monkeypatch, capsys):
    monkeypatch.delenv("PANEL_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("PANEL_ADMIN_USER", "genadmin")
    assert user_count() == 0
    user = bootstrap_admin()
    assert user["username"] == "genadmin"
    assert "generated password" in capsys.readouterr().out


@pytest.mark.integration
def test_session_helpers(auth_app, test_user):
    with auth_app.test_request_context():
        login_user(test_user["id"], test_user["username"])
        assert current_user_id() == test_user["id"]
        assert current_username() == test_user["username"]
        status = auth_status()
        assert status["authenticated"] is True
        assert status["user"]["username"] == test_user["username"]

        logout_user()
        assert current_user_id() is None
        assert auth_status()["authenticated"] is False


@pytest.mark.integration
def test_auth_status_clears_stale_session(auth_app, db):
    with auth_app.test_request_context():
        session["user_id"] = 99999
        session["username"] = "ghost"
        status = auth_status()
        assert status["authenticated"] is False
        assert "user_id" not in session


@pytest.mark.integration
def test_login_required_decorator(auth_app, test_user):
    @login_required
    def protected():
        return jsonify({"user_id": g.user_id, "username": g.username})

    with auth_app.test_request_context():
        resp, code = protected()
        assert code == 401

    with auth_app.test_request_context():
        login_user(test_user["id"], test_user["username"])
        resp = protected()
        assert resp.get_json()["user_id"] == test_user["id"]
