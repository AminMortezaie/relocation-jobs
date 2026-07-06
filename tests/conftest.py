"""Shared fixtures: in-memory Postgres mock and catalog seed data."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from tests.helpers.postgres_mock import install_session_postgres_mock

FIXTURES = Path(__file__).parent / "fixtures"

_SESSION_ENV_KEYS = (
    "PANEL_ADMIN_USER",
    "PANEL_ADMIN_PASSWORD",
    "PANEL_SECRET_KEY",
    "PANEL_ALLOW_REGISTER",
    "PANEL_SCRAPE_ENABLED",
)


@pytest.fixture(scope="session", autouse=True)
def _session_env():
    env_defaults = {
        "PANEL_ADMIN_USER": "admin",
        "PANEL_ADMIN_PASSWORD": "adminpass123",
        "PANEL_SECRET_KEY": "test-secret-key-fixed",
        "PANEL_ALLOW_REGISTER": "1",
        "PANEL_SCRAPE_ENABLED": "0",
    }
    saved = {key: os.environ.get(key) for key in _SESSION_ENV_KEYS}
    for key, value in env_defaults.items():
        os.environ[key] = value
    yield
    for key in _SESSION_ENV_KEYS:
        prior = saved[key]
        if prior is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prior


@pytest.fixture(scope="session")
def _session_postgres(_session_env):
    import relocation_jobs.core.db as core
    from relocation_jobs.core.auth import bootstrap_admin
    from relocation_jobs.db import init_db

    saved_url = os.environ.get("DATABASE_URL")
    original_connect = core._connect_postgres
    fake = install_session_postgres_mock()
    init_db()
    bootstrap_admin()

    yield fake

    fake.close()
    core._connect_postgres = original_connect
    core._pg_conn = None
    core.reset_db_initialized()
    if saved_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = saved_url


@pytest.fixture(autouse=True)
def reset_custom_cities_cache():
    from relocation_jobs.catalog.cache import invalidate_country_cache
    from relocation_jobs.core.location_tags import (
        _invalidate_custom_cities_cache,
        _invalidate_custom_countries_cache,
    )

    _invalidate_custom_cities_cache()
    _invalidate_custom_countries_cache()
    invalidate_country_cache()
    yield
    _invalidate_custom_cities_cache()
    _invalidate_custom_countries_cache()
    invalidate_country_cache()


@pytest.fixture(autouse=True)
def _app_schema(db):
    from relocation_jobs.core.db import get_connection
    from relocation_jobs.db.migrate import apply_v2_migrations
    from relocation_jobs.fetch import runner as fetch_runner
    from relocation_jobs.fetch.repo import clear_running_fetch_runs_for_tests

    apply_v2_migrations(get_connection())
    get_connection().execute("DELETE FROM company_fetch_attempts")
    clear_running_fetch_runs_for_tests()
    with fetch_runner._fetch_lock:
        fetch_runner._fetch_state.clear()
        fetch_runner._fetch_state.update(fetch_runner._idle_fetch_status())
    yield


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("PANEL_DATA_DIR", str(data_dir))
    yield data_dir


@pytest.fixture
def db(tmp_data_dir, _session_postgres, request):
    import relocation_jobs.core.auth as auth_mod
    import relocation_jobs.core.db as core

    if _session_postgres.closed:
        install_session_postgres_mock()
        core.reset_db_initialized()
        from relocation_jobs.db import init_db

        init_db()
        auth_mod.bootstrap_admin()
    elif request.node.get_closest_marker("fresh_db"):
        _session_postgres.clear_data()
    else:
        _session_postgres.clear_tracking()
    core._pg_conn = _session_postgres
    yield
    if request.node.get_closest_marker("fresh_db"):
        _session_postgres.clear_data()
        auth_mod.bootstrap_admin()
    else:
        _session_postgres.clear_tracking()


@pytest.fixture(scope="session")
def app(_session_postgres):
    from unittest.mock import patch

    import relocation_jobs.web.server as panel

    panel._bootstrapped = False
    with patch("relocation_jobs.db.init_db"), patch(
        "relocation_jobs.core.auth.bootstrap_admin"
    ):
        panel.bootstrap_app()
    panel.app.config["TESTING"] = True
    yield panel.app
    panel._bootstrapped = False


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client, db):
    import relocation_jobs.core.auth as auth_mod
    import relocation_jobs.core.db as core
    from relocation_jobs.db import get_user_by_username

    core._pg_conn = core.get_connection()
    if get_user_by_username("admin") is None:
        auth_mod.bootstrap_admin()
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass123"},
    )
    assert resp.status_code == 200
    yield client


@pytest.fixture
def v2_app(app):
    return app


@pytest.fixture
def v2_client(client):
    return client


@pytest.fixture
def v2_auth_client(auth_client):
    return auth_client


@pytest.fixture
def sample_country_data():
    path = FIXTURES / "country_uk_minimal.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def seeded_catalog(db, sample_country_data):
    from relocation_jobs.catalog.writes import save_country_catalog

    data = copy.deepcopy(sample_country_data)
    save_country_catalog("uk", data)
    return data


@pytest.fixture
def seeded_catalog_v2(db):
    from tests.helpers.seed import seed_country

    return seed_country("uk", FIXTURES / "country_uk_minimal.json")


@pytest.fixture
def test_user(db):
    from relocation_jobs.db import create_user
    from tests.helpers.passwords import hash_test_password

    return create_user("testuser", hash_test_password("testpass123"))


@pytest.fixture
def mcp_documents(db):
    from relocation_jobs.mcp import repo as mcp_repo
    from relocation_jobs.mcp.types import ApplicationProfile
    from tests.mcp.conftest import GO_MASTER_TEX, JAVA_MASTER_TEX

    mcp_repo.save_master_resume(1, "go", GO_MASTER_TEX, label="Go backend")
    mcp_repo.save_master_resume(1, "java", JAVA_MASTER_TEX, label="Java backend")
    mcp_repo.save_profile(1, ApplicationProfile(full_name="Test User", email="test@example.com"))
    yield
