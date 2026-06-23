"""Catalog Postgres schema initialization and migrations."""

from __future__ import annotations

from relocation_jobs.core.db import db_transaction
from relocation_jobs.core.migrations import run_migration_once

def convert_text_to_jsonb(conn, table: str, column: str) -> None:
    """Safely convert TEXT JSON column to JSONB if not already done."""
    savepoint = f"jsonb_{table}_{column}"
    try:
        conn.execute(f"SAVEPOINT {savepoint}")
        conn.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE jsonb USING COALESCE({column}::jsonb, '[]'::jsonb)"
        )
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")


def migrate_columns_to_jsonb(conn) -> None:
    """Migrate TEXT JSON columns to JSONB."""
    convert_text_to_jsonb(conn, "companies", "sources_json")
    convert_text_to_jsonb(conn, "companies", "cities_json")
    convert_text_to_jsonb(conn, "companies", "locations_json")
    convert_text_to_jsonb(conn, "matching_jobs", "locations_json")


_country_cache: dict[str, dict | None] = {}
_country_cache_lock = threading.Lock()


def invalidate_country_cache(country_key: str | None = None) -> None:
    """Drop cached catalog reads after writes (country_key=None clears all)."""
    with _country_cache_lock:
        if country_key is None:
            _country_cache.clear()
        else:
            _country_cache.pop(country_key, None)


def country_key_from_filename(name: str) -> str | None:
    m = re.match(r"(\w+)_companies\.json", Path(name).name)
    return m.group(1) if m else None


def _visa_to_db(value) -> int | None:
    if value is True:
        return 1
    if value is False:
        return 0
    return None


def _visa_from_db(value) -> bool | None:
    if value is None:
        return None
    return bool(value)


def init_catalog_schema() -> None:
    from relocation_jobs.core.migrations import run_migration_once

    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS country_meta (
                country TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT '',
                fetched TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL DEFAULT '',
                jobs_fetched TEXT NOT NULL DEFAULT '',
                total INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                country TEXT NOT NULL,
                name TEXT NOT NULL,
                city TEXT NOT NULL DEFAULT '',
                size TEXT NOT NULL DEFAULT '',
                careers_url TEXT NOT NULL DEFAULT '',
                ats_type TEXT NOT NULL DEFAULT '',
                ats_url TEXT NOT NULL DEFAULT '',
                fetch_problem INTEGER NOT NULL DEFAULT 0,
                fetch_problem_date TEXT,
                added TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL DEFAULT '',
                sources_json TEXT NOT NULL DEFAULT '[]',
                UNIQUE(country, name)
            );

            CREATE TABLE IF NOT EXISTS matching_jobs (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                idempotency_key TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                fetched TEXT NOT NULL DEFAULT '',
                last_seen TEXT NOT NULL DEFAULT '',
                visa_sponsorship INTEGER,
                UNIQUE(company_id, idempotency_key)
            );

            CREATE INDEX IF NOT EXISTS idx_companies_country ON companies(country);
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON matching_jobs(company_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_idempotency ON matching_jobs(idempotency_key);
            """
        )

        def _apply_catalog_extra_columns(c) -> None:
            _ensure_company_columns(c)
            _ensure_job_columns(c)
            _ensure_country_meta_columns(c)

        run_migration_once(conn, "catalog_extra_columns_v1", _apply_catalog_extra_columns)
        run_migration_once(conn, "catalog_jsonb_columns_v1", migrate_columns_to_jsonb)


def _ensure_country_meta_columns(conn) -> None:
    conn.execute(
        "ALTER TABLE country_meta ADD COLUMN IF NOT EXISTS last_fetch_new_jobs INTEGER NOT NULL DEFAULT 0"
    )


def _ensure_company_columns(conn) -> None:
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS fetch_ok INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS fetch_ok_date TEXT"
    )
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS cities_json TEXT NOT NULL DEFAULT '[]'"
    )
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS locations_json TEXT NOT NULL DEFAULT '[]'"
    )


def _ensure_job_columns(conn) -> None:
    conn.execute(
        "ALTER TABLE matching_jobs ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE matching_jobs ADD COLUMN IF NOT EXISTS locations_json TEXT NOT NULL DEFAULT '[]'"
    )
