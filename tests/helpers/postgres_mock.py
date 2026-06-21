"""Fake psycopg connection backed by in-memory SQLite for postgres code paths."""

from __future__ import annotations

import re
import sqlite3
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
        try:
            return self._conn.execute(sql, params)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column name" in msg or "already exists" in msg:
                return self._conn.execute("SELECT 1 AS ok")
            raise

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
        return out, returning


def install_postgres_mock(monkeypatch, *, database_url: str = "postgresql://test:test@localhost/test") -> FakePgConnection:
    """Monkeypatch db layer to use fake postgres connection."""
    import relocation_jobs.db as db_module

    fake = FakePgConnection()
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr("relocation_jobs.db_backend.use_postgres", lambda: True)
    monkeypatch.setattr("relocation_jobs.catalog_db.use_postgres", lambda: True)
    db_module._sqlite_conn = None
    db_module._pg_conn = None

    def _connect():
        nonlocal fake
        fake = FakePgConnection()
        return fake

    monkeypatch.setattr(db_module, "_connect_postgres", _connect)
    return fake
