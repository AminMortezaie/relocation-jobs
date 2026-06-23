"""Shared fixtures: in-memory Postgres mock, catalog seed data, Flask test client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _reset_db_connections() -> None:
    import relocation_jobs.core.db as core

    if core._pg_conn is not None and not core._pg_conn.closed:
        core._pg_conn.close()
    core._pg_conn = None
    core.reset_db_initialized()


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
    """Point panel storage at a temp directory; use in-memory Postgres mock."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("PANEL_DATA_DIR", str(data_dir))
    _reset_db_connections()
    yield data_dir
    _reset_db_connections()


@pytest.fixture
def db(tmp_data_dir, monkeypatch):
    from tests.helpers.postgres_mock import install_postgres_mock
    from relocation_jobs.db import init_db

    install_postgres_mock(monkeypatch)
    init_db()
    yield
    _reset_db_connections()


@pytest.fixture
def sample_country_data():
    path = FIXTURES / "country_uk_minimal.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def seeded_catalog(db, sample_country_data):
    from relocation_jobs.catalog_db import save_country

    save_country("uk", sample_country_data)
    return sample_country_data


@pytest.fixture
def test_user(db):
    from werkzeug.security import generate_password_hash

    from relocation_jobs.db import create_user

    return create_user("testuser", generate_password_hash("testpass123"))


@pytest.fixture
def app_client(db, monkeypatch):
    monkeypatch.setenv("PANEL_ADMIN_USER", "admin")
    monkeypatch.setenv("PANEL_ADMIN_PASSWORD", "adminpass123")
    monkeypatch.setenv("PANEL_SECRET_KEY", "test-secret-key-fixed")
    monkeypatch.setenv("PANEL_ALLOW_REGISTER", "1")
    monkeypatch.setenv("PANEL_SCRAPE_ENABLED", "0")

    import relocation_jobs.panel_server as panel_server

    panel_server._bootstrapped = False
    panel_server.bootstrap_app()
    panel_server.app.config["TESTING"] = True

    with panel_server.app.test_client() as client:
        yield client


@pytest.fixture
def pg_db(db):
    """Alias for db — all tests now use the Postgres mock."""
    yield


@pytest.fixture
def auth_client(app_client):
    resp = app_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass123"},
    )
    assert resp.status_code == 200
    return app_client
