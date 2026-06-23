"""Shared fixtures: in-memory Postgres mock, catalog seed data, Flask test client."""

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


def _reset_db_connections() -> None:
    import relocation_jobs.core.db as core

    if core._pg_conn is not None and not core._pg_conn.closed:
        core._pg_conn.close()
    core._pg_conn = None
    core.reset_db_initialized()


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
    """One in-memory DB for the session; schema migrated once, rows cleared per test."""
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


@pytest.fixture(scope="session")
def _flask_app(_session_postgres):
    """Bootstrap the panel Flask app once per session (expensive import + init_auth)."""
    from unittest.mock import patch

    import relocation_jobs.panel_server as panel_server

    panel_server._bootstrapped = False
    with patch("relocation_jobs.core.auth.init_db"), patch(
        "relocation_jobs.core.auth.bootstrap_admin"
    ):
        panel_server.bootstrap_app()
    panel_server.app.config["TESTING"] = True

    yield panel_server.app

    panel_server._bootstrapped = False


@pytest.fixture(scope="session")
def _session_test_client(_flask_app):
    client = _flask_app.test_client()
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass123"},
    )
    return client


@pytest.fixture(autouse=True)
def reset_custom_cities_cache():
    """Custom city loader caches by path; clear between tests."""
    from relocation_jobs.core.location_tags import _invalidate_custom_cities_cache
    from relocation_jobs.catalog_db import invalidate_country_cache

    _invalidate_custom_cities_cache()
    invalidate_country_cache()
    yield
    _invalidate_custom_cities_cache()
    invalidate_country_cache()


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Point panel storage at a temp directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("PANEL_DATA_DIR", str(data_dir))
    yield data_dir


@pytest.fixture
def db(tmp_data_dir, _session_postgres, request):
    """Reset per-user rows between tests; full wipe only for ``fresh_db`` tests."""
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


@pytest.fixture
def panel_db(db):
    yield


@pytest.fixture
def sample_country_data():
    path = FIXTURES / "country_uk_minimal.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def seeded_catalog(db, sample_country_data):
    from relocation_jobs.catalog_db import save_country_catalog

    data = copy.deepcopy(sample_country_data)
    save_country_catalog("uk", data)
    return data


@pytest.fixture
def test_user(db):
    from relocation_jobs.db import create_user
    from tests.helpers.passwords import hash_test_password

    return create_user("testuser", hash_test_password("testpass123"))


@pytest.fixture
def app_client(_session_test_client):
    with _session_test_client.session_transaction() as sess:
        sess.clear()
    yield _session_test_client


@pytest.fixture
def pg_db(db):
    """Alias for db — all tests now use the Postgres mock."""
    yield


@pytest.fixture
def auth_client(_session_test_client, _session_postgres):
    import relocation_jobs.core.auth as auth_mod
    import relocation_jobs.core.db as core
    from relocation_jobs.db import get_user_by_username

    core._pg_conn = _session_postgres
    if get_user_by_username("admin") is None:
        auth_mod.bootstrap_admin()
    with _session_test_client.session_transaction() as sess:
        sess.clear()
    resp = _session_test_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass123"},
    )
    assert resp.status_code == 200
    yield _session_test_client


_SCRAPE_ONLY_TESTS = frozenset({
    "test_discover_careers_playwright_button_click",
    "test_discover_careers_playwright_button_inner_text_error",
    "test_discover_from_relocate_paths",
    "test_discover_careers_static_non_http_href",
    "test_discover_careers_url_playwright_fallback",
    "test_build_companies_main_module_entry",
    "test_build_companies_resolve_country_alias",
    "test_panel_server_scrape_helpers",
    "test_panel_server_scrape_exception",
    "test_panel_fetch_endpoints",
    "test_run_scrape_mocked_subprocess",
    "test_detect_ats_and_enrich",
})


def pytest_collection_modifyitems(items):
    """Tag scraper tests so default CI runs business logic only."""
    for item in items:
        nodeid = item.nodeid
        if (
            "/test_scrape_" in nodeid
            or "/test_build_companies.py" in nodeid
            or item.name in _SCRAPE_ONLY_TESTS
        ):
            item.add_marker(pytest.mark.scrape)
