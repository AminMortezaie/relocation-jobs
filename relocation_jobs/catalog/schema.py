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


def init_catalog_schema() -> None:
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

            CREATE TABLE IF NOT EXISTS custom_countries (
                country TEXT PRIMARY KEY,
                label TEXT NOT NULL
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
        run_migration_once(conn, "catalog_job_description_v1", _ensure_job_description_column)
        from relocation_jobs.catalog.custom_countries import (
            migrate_custom_countries_from_json,
            seed_default_countries,
        )

        run_migration_once(conn, "custom_countries_seed_defaults_v1", seed_default_countries)
        run_migration_once(conn, "custom_countries_json_import_v1", migrate_custom_countries_from_json)
        run_migration_once(conn, "catalog_kind_v1", _migrate_catalog_kind_v1)
        run_migration_once(conn, "remotedxb_to_remote_dxb_v1", _migrate_remotedxb_to_remote_dxb_v1)


def _ensure_job_description_column(conn) -> None:
    conn.execute(
        "ALTER TABLE matching_jobs ADD COLUMN IF NOT EXISTS description_text TEXT NOT NULL DEFAULT ''"
    )


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
    conn.execute(
        "ALTER TABLE matching_jobs ADD COLUMN IF NOT EXISTS description_text TEXT NOT NULL DEFAULT ''"
    )


def _migrate_catalog_kind_v1(conn) -> None:
    conn.execute(
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS catalog_kind TEXT NOT NULL DEFAULT 'relocation'
        """
    )
    conn.execute(
        """
        UPDATE companies
        SET catalog_kind = 'remote'
        WHERE country IN ('remote-ok', 'remote-dxb')
           OR LOWER(TRIM(ats_type)) IN ('remoteok', 'remotedxb', 'sourced')
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_companies_catalog_kind
        ON companies(catalog_kind)
        """
    )


def _migrate_remotedxb_to_remote_dxb_v1(conn) -> None:
    conn.execute(
        """
        INSERT INTO custom_countries (country, label)
        VALUES ('remote-dxb', 'Remote DXB')
        ON CONFLICT (country) DO UPDATE SET label = EXCLUDED.label
        """
    )
    rows = conn.execute(
        """
        SELECT id, name
        FROM companies
        WHERE country = 'uae'
          AND (
            LOWER(TRIM(ats_type)) = 'remotedxb'
            OR LOWER(TRIM(ats_type)) = 'sourced'
          )
        """
    ).fetchall()
    names: list[str] = []
    for row in rows:
        data = dict(row) if not isinstance(row, dict) else row
        ats_row = conn.execute(
            "SELECT ats_type, sources_json FROM companies WHERE id = %s",
            (data["id"],),
        ).fetchone()
        ats_data = dict(ats_row) if ats_row is not None and not isinstance(ats_row, dict) else (ats_row or {})
        ats = (ats_data.get("ats_type") or "").strip().lower()
        sources_raw = str(ats_data.get("sources_json") or "").lower()
        if ats == "sourced" and "remotedxb" not in sources_raw:
            continue
        names.append(data["name"])
        conn.execute(
            """
            UPDATE companies
            SET country = 'remote-dxb', catalog_kind = 'remote'
            WHERE id = %s
            """,
            (data["id"],),
        )
    if not names:
        return
    placeholders = ", ".join("%s" for _ in names)
    params = ("remote-dxb", "uae", *names)
    for table in (
        "job_tracking",
        "company_tracking",
        "job_status_events",
        "mcp_applications",
    ):
        try:
            conn.execute(
                f"""
                UPDATE {table}
                SET country = %s
                WHERE country = %s AND company_name IN ({placeholders})
                """,
                params,
            )
        except Exception:
            continue
    count_row = conn.execute(
        "SELECT COUNT(*) AS n FROM companies WHERE country = %s",
        ("remote-dxb",),
    ).fetchone()
    total = int((dict(count_row) if count_row is not None and not isinstance(count_row, dict) else (count_row or {})).get("n") or 0)
    conn.execute(
        """
        INSERT INTO country_meta (country, source, fetched, updated, jobs_fetched, total)
        VALUES (%s, '', '', '', '', %s)
        ON CONFLICT (country) DO UPDATE SET total = EXCLUDED.total
        """,
        ("remote-dxb", total),
    )
