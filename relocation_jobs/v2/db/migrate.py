from __future__ import annotations

from relocation_jobs.core.migrations import run_migration_once


def _company_fetch_attempts_v1(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_fetch_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_run_id INTEGER,
            country TEXT NOT NULL,
            company_name TEXT NOT NULL,
            careers_url TEXT,
            ats_type TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            jobs_total INTEGER,
            jobs_new INTEGER,
            jobs_preserved INTEGER,
            message TEXT,
            duration_seconds REAL
        )
        """
    )


def apply_v2_migrations(conn) -> None:
    run_migration_once(conn, "v2_company_fetch_attempts_v1", _company_fetch_attempts_v1)
