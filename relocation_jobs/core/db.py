"""Postgres connection management and database initialisation."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from relocation_jobs.core.job_identity import normalize_job_url

try:
    from psycopg import OperationalError as _PgOperationalError
except ImportError:  # pragma: no cover
    _PgOperationalError = Exception  # type: ignore[misc,assignment]

_db_lock = threading.RLock()
_pg_conn = None
_db_initialized = False


def reset_db_initialized() -> None:
    global _db_initialized
    _db_initialized = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_url(url: str) -> str:
    return normalize_job_url(url)


def _connect_postgres():
    import psycopg  # local import so tests can monkeypatch sys.modules["psycopg"]
    from psycopg.rows import dict_row

    return psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
        autocommit=True,
    )


def _reset_pg_connection() -> None:
    global _pg_conn
    if _pg_conn is not None:
        try:
            _pg_conn.close()
        except Exception:
            pass
    _pg_conn = None


def get_connection():
    global _pg_conn
    if _pg_conn is None or _pg_conn.closed:
        _pg_conn = _connect_postgres()
    return _pg_conn


@contextmanager
def db_read():
    """Serialize catalog reads with writes on the shared DB connection."""
    with _db_lock:
        try:
            yield get_connection()
        except _PgOperationalError:
            # Connection was dropped by the server (e.g. Neon idle timeout, SSL drop).
            # Reset so the next get_connection() creates a fresh connection.
            _reset_pg_connection()
            raise


@contextmanager
def db_transaction():
    with _db_lock:
        conn = get_connection()
        try:
            with conn.transaction():
                yield conn
        except _PgOperationalError:
            _reset_pg_connection()
            raise
        except Exception:
            if conn.closed:
                _reset_pg_connection()
            raise


def init_db(*, force: bool = False) -> None:
    global _db_initialized
    if _db_initialized and not force:
        return

    # Lazy imports to break the core → migrations → events → core cycle.
    from relocation_jobs.catalog_db import init_catalog_schema
    from relocation_jobs.core.migrations import _migrate_schema

    init_catalog_schema()
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_tracking (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                country TEXT NOT NULL,
                company_name TEXT NOT NULL,
                job_url TEXT NOT NULL,
                applied INTEGER NOT NULL DEFAULT 0,
                applied_date TEXT,
                not_for_me INTEGER NOT NULL DEFAULT 0,
                not_for_me_date TEXT,
                rejected INTEGER NOT NULL DEFAULT 0,
                rejected_date TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, country, company_name, job_url)
            );

            CREATE TABLE IF NOT EXISTS company_tracking (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                country TEXT NOT NULL,
                company_name TEXT NOT NULL,
                company_applied INTEGER NOT NULL DEFAULT 0,
                company_applied_date TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, country, company_name)
            );

            CREATE INDEX IF NOT EXISTS idx_job_tracking_user ON job_tracking(user_id);
            CREATE INDEX IF NOT EXISTS idx_company_tracking_user ON company_tracking(user_id);

            CREATE TABLE IF NOT EXISTS fetch_runs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                country TEXT NOT NULL,
                company_name TEXT,
                scope TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                duration_seconds REAL,
                exit_code INTEGER,
                cancelled INTEGER NOT NULL DEFAULT 0,
                new_jobs INTEGER NOT NULL DEFAULT 0,
                concurrency INTEGER,
                companies_done INTEGER,
                companies_total INTEGER,
                result_line TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_fetch_runs_user_started
                ON fetch_runs(user_id, started_at DESC);
            """
        )
        _migrate_schema(conn)
    _db_initialized = True
