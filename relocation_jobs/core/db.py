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
_pg_conn_last_used: float = 0.0
_db_initialized = False

# Thread-local storage: each thread gets its own DB connection.
_thread_local = threading.local()

# Neon free tier suspends compute after ~5 min idle; ping before that threshold.
_IDLE_PING_THRESHOLD_S = 270.0  # 4.5 minutes


class _RetryConnection:
    """Proxy that reconnects once when a query hits a dropped SSL connection."""

    def __init__(self, conn, *, thread_owned: bool = False):
        self._conn = conn
        self._thread_owned = thread_owned

    def _reconnect(self):
        if self._thread_owned:
            self._conn = _connect_postgres()
            _thread_local.conn = self._conn
            _thread_local.last_used = __import__("time").monotonic()
        else:
            _reset_pg_connection()
            self._conn = _acquire_connection()

    def execute(self, sql, params=()):
        try:
            return self._conn.execute(sql, params)
        except _PgOperationalError:
            self._reconnect()
            return self._conn.execute(sql, params)

    def executemany(self, sql, params_seq):
        try:
            return self._conn.executemany(sql, params_seq)
        except _PgOperationalError:
            self._reconnect()
            return self._conn.executemany(sql, params_seq)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


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
        connect_timeout=10,
        # Neon pooler rejects server-side prepared statements.
        prepare_threshold=None,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def _reset_pg_connection() -> None:
    global _pg_conn, _pg_conn_last_used
    if _pg_conn is not None:
        try:
            _pg_conn.close()
        except Exception:
            pass
    _pg_conn = None
    _pg_conn_last_used = 0.0


def _acquire_connection():
    """Return the shared connection, reconnecting when idle or closed."""
    import time

    global _pg_conn, _pg_conn_last_used
    now = time.monotonic()
    if _pg_conn is None or _pg_conn.closed:
        _pg_conn = _connect_postgres()
        _pg_conn_last_used = now
    elif now - _pg_conn_last_used > _IDLE_PING_THRESHOLD_S:
        try:
            _pg_conn.execute("SELECT 1")
        except Exception:
            _reset_pg_connection()
            _pg_conn = _connect_postgres()
        _pg_conn_last_used = now
    else:
        _pg_conn_last_used = now
    return _pg_conn


def _acquire_thread_connection():
    """Return a per-thread connection, creating one if needed."""
    import time

    conn = getattr(_thread_local, "conn", None)
    last_used = getattr(_thread_local, "last_used", 0.0)
    now = time.monotonic()

    if conn is None or conn.closed:
        conn = _connect_postgres()
        _thread_local.conn = conn
        _thread_local.last_used = now
        return conn

    if now - last_used > _IDLE_PING_THRESHOLD_S:
        try:
            conn.execute("SELECT 1")
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            conn = _connect_postgres()
            _thread_local.conn = conn
        _thread_local.last_used = now
    else:
        _thread_local.last_used = now
    return conn


def _is_main_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


def get_connection():
    """Thread-safe access to a Postgres connection.

    Main thread uses the shared connection (with lock).
    Other threads get their own connection (no lock contention).
    """
    if _is_main_thread():
        with _db_lock:
            return _RetryConnection(_acquire_connection())
    return _RetryConnection(_acquire_thread_connection(), thread_owned=True)


@contextmanager
def db_read():
    """Scoped DB read — per-thread connection for worker threads."""
    if _is_main_thread():
        with _db_lock:
            try:
                yield _RetryConnection(_acquire_connection())
            except _PgOperationalError:
                _reset_pg_connection()
                raise
    else:
        conn = _acquire_thread_connection()
        try:
            yield _RetryConnection(conn, thread_owned=True)
        except _PgOperationalError:
            try:
                conn.close()
            except Exception:
                pass
            _thread_local.conn = None
            raise


@contextmanager
def db_transaction():
    if _is_main_thread():
        with _db_lock:
            conn = _acquire_connection()
            try:
                with conn.transaction():
                    yield _RetryConnection(conn)
            except _PgOperationalError:
                _reset_pg_connection()
                raise
            except Exception:
                if conn.closed:
                    _reset_pg_connection()
                raise
    else:
        conn = _acquire_thread_connection()
        try:
            with conn.transaction():
                yield _RetryConnection(conn, thread_owned=True)
        except _PgOperationalError:
            try:
                conn.close()
            except Exception:
                pass
            _thread_local.conn = None
            raise
        except Exception:
            if conn.closed:
                _thread_local.conn = None
            raise


def init_db(*, force: bool = False) -> None:
    global _db_initialized
    if _db_initialized and not force:
        return

    # Lazy imports to break the core → migrations → events → core cycle.
    from relocation_jobs.catalog.schema import init_catalog_schema
    from relocation_jobs.core.migrations import _migrate_schema

    init_catalog_schema()
    from relocation_jobs.catalog.custom_countries import init_countries_store

    init_countries_store()
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
