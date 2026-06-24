from __future__ import annotations

from pathlib import Path

import pytest

from relocation_jobs.core.db import get_connection
from relocation_jobs.v2.db.migrate import apply_v2_migrations

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def _v2_schema(db):
    from relocation_jobs.core.db import get_connection

    apply_v2_migrations(get_connection())
    get_connection().execute("DELETE FROM company_fetch_attempts")
    yield


@pytest.fixture(scope="session")
def v2_app(_session_postgres):
    from unittest.mock import patch

    import relocation_jobs.v2.web.server as v2_server

    v2_server._bootstrapped = False
    with patch("relocation_jobs.db.init_db"), patch(
        "relocation_jobs.core.auth.bootstrap_admin"
    ):
        v2_server.bootstrap_app()
    v2_server.app.config["TESTING"] = True
    yield v2_server.app
    v2_server._bootstrapped = False


@pytest.fixture
def v2_client(v2_app):
    return v2_app.test_client()


@pytest.fixture
def v2_auth_client(v2_client, db):
    import relocation_jobs.core.auth as auth_mod
    import relocation_jobs.core.db as core
    from relocation_jobs.db import get_user_by_username

    core._pg_conn = core.get_connection()
    if get_user_by_username("admin") is None:
        auth_mod.bootstrap_admin()
    with v2_client.session_transaction() as sess:
        sess.clear()
    resp = v2_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass123"},
    )
    assert resp.status_code == 200
    yield v2_client


@pytest.fixture
def seeded_catalog_v2(db):
    from tests.v2.helpers.seed import seed_country

    return seed_country("uk", FIXTURES / "country_uk_minimal.json")
