"""Fake psycopg connection backed by in-memory SQLite for postgres code paths."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Any


class _PgRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _PgShimCursor:
    def __init__(self, cur: sqlite3.Cursor, lastrowid: int | None = None):
        self._cur = cur
        self._lastrowid = lastrowid

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def fetchone(self) -> _PgRow | None:
        row = self._cur.fetchone()
        if row is not None:
            return _PgRow(row)
        if self._lastrowid is not None:
            return _PgRow({"id": self._lastrowid})
        return None

    def fetchall(self) -> list[_PgRow]:
        return [_PgRow(r) for r in self._cur.fetchall()]


class FakePgConnection:
    """Minimal psycopg-like connection for exercising ``use_postgres()`` branches."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.closed = False
        self.autocommit = True

    @contextmanager
    def transaction(self):
        try:
            yield self
            self.commit()
        except Exception:
            self.rollback()
            raise

    def execute(self, sql: str, params: tuple | list = ()) -> _PgShimCursor:
        adapted, returning = self._adapt(sql)
        if ";" in adapted and adapted.strip().count(";") > 0:
            parts = [p.strip() for p in adapted.split(";") if p.strip()]
            cur = None
            lastrowid = None
            for i, part in enumerate(parts):
                cur = self._run(part, params if i == len(parts) - 1 else ())
                lastrowid = cur.lastrowid
            assert cur is not None
            return _PgShimCursor(cur, lastrowid if returning else None)

        cur = self._run(adapted, params)
        return _PgShimCursor(cur, cur.lastrowid if returning else None)

    def _run(self, sql: str, params: tuple | list) -> sqlite3.Cursor:
        sql, params = self._adapt_any(sql, params)
        try:
            return self._conn.execute(sql, params)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column name" in msg or "already exists" in msg:
                return self._conn.execute("SELECT 1 AS ok")
            if "cannot add a column" in msg and "alter table" in msg.lower():
                return self._conn.execute("SELECT 1 AS ok")
            raise

    def _adapt_any(self, sql: str, params: tuple | list) -> tuple[str, tuple]:
        """Translate PostgreSQL ``= ANY(?)`` with a list param to ``IN (?, ?, ...)``."""
        if "= ANY(?)" not in sql:
            return sql, params
        params = list(params)
        parts = sql.split("= ANY(?)")
        if len(parts) != 2:
            return sql, tuple(params)
        list_param = params.pop(params.index(next(p for p in params if isinstance(p, (list, tuple)))))
        in_clause = ", ".join("?" for _ in list_param)
        sql = f"{parts[0]}IN ({in_clause}){parts[1]}"
        params.extend(list_param)
        return sql, tuple(params)

    def executemany(self, sql: str, params_seq: list[tuple]) -> None:
        self._conn.executemany(self._adapt(sql)[0], params_seq)

    def executescript(self, sql: str) -> None:
        self._conn.executescript(self._adapt(sql)[0])

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self.closed = True
        self._conn.close()

    _DATA_TABLES = (
        "job_status_events",
        "fetch_runs",
        "job_tracking",
        "company_tracking",
        "matching_jobs",
        "companies",
        "country_meta",
        "users",
    )

    _TRACKING_TABLES = (
        "job_status_events",
        "fetch_runs",
        "company_fetch_attempts",
        "job_tracking",
        "company_tracking",
    )

    def clear_data(self) -> None:
        """Delete all rows but keep schema — fast reset between tests."""
        self._conn.execute("PRAGMA foreign_keys = OFF")
        for table in self._DATA_TABLES:
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.execute("DELETE FROM sqlite_sequence")
        self._conn.commit()
        self._conn.execute("PRAGMA foreign_keys = ON")

    def clear_tracking(self, *, keep_admin: str = "admin") -> None:
        """Clear per-user state but keep catalog companies/jobs."""
        self._conn.execute("PRAGMA foreign_keys = OFF")
        for table in self._TRACKING_TABLES:
            try:
                self._conn.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass
        self._conn.execute(
            "DELETE FROM users WHERE LOWER(username) != LOWER(?)",
            (keep_admin,),
        )
        self._conn.commit()
        self._conn.execute("PRAGMA foreign_keys = ON")

    def _adapt(self, sql: str) -> tuple[str, bool]:
        returning = bool(re.search(r"\bRETURNING\b", sql, re.I))
        out = sql.replace("%s", "?")
        out = re.sub(r"\bSERIAL PRIMARY KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", out, flags=re.I)
        out = re.sub(r"\bEXCLUDED\.", "excluded.", out)
        out = re.sub(
            r"ADD COLUMN IF NOT EXISTS",
            "ADD COLUMN",
            out,
            flags=re.I,
        )
        out = re.sub(r"\bJSONB\b", "TEXT", out, flags=re.I)
        out = re.sub(r"'::(jsonb|text)", "'", out, flags=re.I)
        return out, returning


def install_postgres_mock(monkeypatch, *, database_url: str = "postgresql://test:test@localhost/test") -> FakePgConnection:
    """Monkeypatch db layer to use in-memory fake Postgres connection."""
    import relocation_jobs.core.db as core

    fake = FakePgConnection()
    monkeypatch.setenv("DATABASE_URL", database_url)
    core._pg_conn = None
    core.reset_db_initialized()

    def _connect():
        nonlocal fake
        fake = FakePgConnection()
        core.reset_db_initialized()
        return fake

    monkeypatch.setattr(core, "_connect_postgres", _connect)
    return fake


def install_session_postgres_mock(
    *,
    database_url: str = "postgresql://test:test@localhost/test",
) -> FakePgConnection:
    """Install a single in-memory connection for the whole test session."""
    import relocation_jobs.core.db as core

    fake = FakePgConnection()
    os.environ["DATABASE_URL"] = database_url
    core._pg_conn = None
    core.reset_db_initialized()

    def _connect():
        return fake

    core._connect_postgres = _connect
    core._pg_conn = fake
    return fake
