"""Module-scoped catalog fixtures for API test files."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from relocation_jobs.catalog_db import save_country

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def rich_catalog_payload(extra: dict | None = None) -> dict:
    data = json.loads((_FIXTURES / "country_uk_minimal.json").read_text(encoding="utf-8"))
    data = copy.deepcopy(data)
    acme = data["companies"][0]
    acme["matching_jobs"][0]["visa_sponsorship"] = True
    acme["matching_jobs"][1]["visa_sponsorship"] = False
    acme.setdefault("locations", [{"country": "uk", "city": "London"}])
    data["companies"].append(
        {
            "name": "Empty Corp",
            "city": "Manchester",
            "locations": [{"country": "uk", "city": "Manchester"}],
            "careers_url": "https://example.co.uk/empty",
            "matching_jobs": [],
        }
    )
    data["companies"].append(
        {
            "name": "Fetch Problem Inc",
            "city": "London",
            "careers_url": "https://example.co.uk/problem",
            "fetch_problem": True,
            "fetch_problem_date": "2025-06-01",
            "matching_jobs": [],
        }
    )
    data["companies"].append(
        {
            "name": "Fetch OK Ltd",
            "city": "London",
            "careers_url": "https://example.co.uk/ok",
            "fetch_ok": True,
            "fetch_ok_date": "2025-06-01",
            "matching_jobs": [],
        }
    )
    if extra:
        data["companies"].extend(extra.get("companies", []))
    return data


@pytest.fixture(scope="module")
def _catalog_template():
    return rich_catalog_payload()


@pytest.fixture(scope="module")
def _module_panel(_session_postgres, _session_test_client, _catalog_template):
    import relocation_jobs.core.db as core

    _session_postgres.clear_data()
    core._pg_conn = _session_postgres
    from relocation_jobs.core.auth import bootstrap_admin

    bootstrap_admin()
    save_country("uk", copy.deepcopy(_catalog_template))
    with _session_test_client.session_transaction() as sess:
        sess.clear()
    resp = _session_test_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass123"},
    )
    assert resp.status_code == 200
    yield
    _session_postgres.clear_data()


@pytest.fixture(autouse=True)
def _module_panel_reset(request, _session_postgres, _catalog_template):
    uses = "_module_panel" in request.fixturenames or "rich_catalog" in request.fixturenames
    if not uses:
        yield
        return
    save_country("uk", copy.deepcopy(_catalog_template))
    _session_postgres.clear_tracking()
    yield
    save_country("uk", copy.deepcopy(_catalog_template))
    _session_postgres.clear_tracking()


@pytest.fixture
def rich_catalog(_module_panel, _catalog_template):
    return copy.deepcopy(_catalog_template)


@pytest.fixture
def seeded_catalog(_module_panel, _catalog_template):
    return copy.deepcopy(_catalog_template)
