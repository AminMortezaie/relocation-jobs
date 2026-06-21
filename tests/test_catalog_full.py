"""Catalog DB edge cases: migration, export, path helpers, upserts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from relocation_jobs.catalog_db import (
    catalog_has_data,
    country_key_from_filename,
    export_all_archives,
    export_country_archive,
    load_country,
    load_country_for_path,
    migrate_from_json_files,
    save_country,
    save_country_for_path,
    touch_country_meta,
    upsert_companies,
    upsert_company,
)
from relocation_jobs.paths import COMPANIES_DIR, data_dir


def test_country_key_from_filename():
    assert country_key_from_filename("uk_companies.json") == "uk"
    assert country_key_from_filename("/path/netherlands_companies.json") == "netherlands"
    assert country_key_from_filename("invalid.json") is None
    assert country_key_from_filename("") is None


@pytest.mark.integration
def test_migrate_from_json_files(tmp_data_dir, db, sample_country_data, monkeypatch):
    from relocation_jobs.db import db_transaction

    monkeypatch.setattr(
        "relocation_jobs.services.catalog_service.COUNTRY_FILE_NAMES",
        {"uk": "uk_companies.json"},
    )

    with db_transaction() as conn:
        conn.execute("DELETE FROM matching_jobs")
        conn.execute("DELETE FROM companies")
        conn.execute("DELETE FROM country_meta")

    assert not catalog_has_data()

    json_path = data_dir() / "uk_companies.json"
    json_path.write_text(json.dumps(sample_country_data), encoding="utf-8")

    imported = migrate_from_json_files()
    assert imported == 1
    assert catalog_has_data()
    assert migrate_from_json_files() == 0


@pytest.mark.integration
def test_export_country_archive(seeded_catalog, tmp_data_dir):
    path = export_country_archive("uk")
    assert path is not None
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source"] == "test-fixture"
    assert export_country_archive("unknown") is None

    paths = export_all_archives()
    assert any(p.name == "uk_companies.json" for p in paths)


@pytest.mark.integration
def test_load_country_for_path_db_and_file(seeded_catalog, sample_country_data, tmp_path):
    key, data = load_country_for_path("uk_companies.json")
    assert key == "uk"
    assert data["companies"][0]["name"] == "Acme Backend Ltd"

    custom = tmp_path / "custom.json"
    custom.write_text(json.dumps({"companies": [], "total": 0}), encoding="utf-8")
    key2, data2 = load_country_for_path(custom)
    assert key2 is None
    assert data2["companies"] == []

    missing_key, missing_data = load_country_for_path(tmp_path / "missing.json")
    assert missing_data == {"companies": [], "total": 0}


@pytest.mark.integration
def test_save_country_for_path(seeded_catalog, tmp_path):
    payload = load_country("uk")
    save_country_for_path("uk_companies.json", payload, export_archive=False)
    assert load_country("uk") is not None

    orphan = tmp_path / "orphan.json"
    save_country_for_path(orphan, {"companies": [], "total": 0})
    assert orphan.is_file()


@pytest.mark.integration
def test_touch_country_meta(db, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)
    touch_country_meta("uk", updated="2025-07-01", total=5, jobs_fetched="2025-07-01")
    loaded = load_country("uk")
    assert loaded["updated"] == "2025-07-01"
    assert loaded["total"] == 5

    touch_country_meta("de", source="new-country", total=0)
    assert load_country("de") is not None

    touch_country_meta("uk", invalid_field="ignored")


@pytest.mark.integration
def test_upsert_company_and_batch(db, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)

    upsert_company(
        "uk",
        {
            "name": "Upsert Co",
            "city": "Manchester",
            "cities": ["Manchester"],
            "matching_jobs": [
                {
                    "title": "Dev",
                    "url": "https://example.com/j/1?gh_jid=1",
                    "fetched": "2025-06-01",
                }
            ],
        },
    )
    loaded = load_country("uk")
    names = {c["name"] for c in loaded["companies"]}
    assert "Upsert Co" in names

    upsert_companies(
        "uk",
        [
            {
                "name": "Batch Co",
                "city": "Leeds",
                "matching_jobs": [],
            }
        ],
        touch_meta=True,
    )
    loaded = load_country("uk")
    assert any(c["name"] == "Batch Co" for c in loaded["companies"])

    upsert_companies("uk", [], touch_meta=False)


@pytest.mark.integration
def test_save_country_removes_absent_companies(db, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)
    slim = {**sample_country_data, "companies": []}
    save_country("uk", slim, export_archive=False)
    assert load_country("uk")["companies"] == []


@pytest.mark.integration
def test_upsert_skips_empty_company_name(db, sample_country_data):
    save_country("uk", sample_country_data, export_archive=False)
    upsert_company("uk", {"name": "  ", "city": "Nowhere"})
    assert len(load_country("uk")["companies"]) == 1


@pytest.mark.integration
def test_company_sources_and_visa_parsing(db):
    save_country(
        "uk",
        {
            "source": "test",
            "companies": [
                {
                    "name": "Visa Co",
                    "city": "London",
                    "sources": ["relocate.me"],
                    "matching_jobs": [
                        {
                            "title": "Role",
                            "url": "https://example.com/v/1?gh_jid=1",
                            "visa_sponsorship": True,
                        },
                        {
                            "title": "No visa",
                            "url": "https://example.com/v/2?gh_jid=2",
                            "visa_sponsorship": False,
                        },
                    ],
                }
            ],
        },
        export_archive=False,
    )
    company = load_country("uk")["companies"][0]
    assert company["sources"] == ["relocate.me"]
    jobs = {j["title"]: j for j in company["matching_jobs"]}
    assert jobs["Role"]["visa_sponsorship"] is True
    assert jobs["No visa"]["visa_sponsorship"] is False
