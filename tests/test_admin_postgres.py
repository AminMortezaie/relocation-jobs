"""Admin dashboard on postgres code paths."""

from __future__ import annotations

import pytest

from relocation_jobs.admin_data import get_admin_overview, get_catalog_overview
from relocation_jobs.catalog_db import save_country
from relocation_jobs.db import list_users_with_stats

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_catalog_pg(pg_db):
    from relocation_jobs.db import db_transaction

    with db_transaction() as conn:
        conn.execute("DELETE FROM matching_jobs")
        conn.execute("DELETE FROM companies")
        conn.execute("DELETE FROM country_meta")
    yield


def test_catalog_overview_on_postgres(isolated_catalog_pg, sample_country_data):
    save_country("uk", sample_country_data)
    overview = get_catalog_overview()
    assert overview["totals"]["companies"] == 1


def test_admin_overview_on_postgres(isolated_catalog_pg, sample_country_data):
    save_country("uk", sample_country_data)
    data = get_admin_overview(fetch_state={"running": False})
    assert data["catalog"]["companies"] == 1


def test_list_users_on_postgres(pg_db):
    users = list_users_with_stats()
    assert isinstance(users, list)


def test_postgres_ad_hoc_reads_then_write(pg_db):
    """Reads via get_connection() must not block later db_transaction() writes."""
    from relocation_jobs.db import db_transaction, get_user_by_id, user_count

    user_count()
    assert get_user_by_id(999_999) is None

    with db_transaction() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    assert row is not None
