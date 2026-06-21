#!/usr/bin/env python3
"""Copy local SQLite panel.db into Postgres (Neon via DATABASE_URL).

Usage:
  1. Create a Neon project → copy the connection string
  2. Add to .env:  DATABASE_URL=postgresql://...?sslmode=require
  3. Run:  python scripts/migrate_sqlite_to_neon.py
  4. Restart the panel server

Keeps row IDs so user/company/job foreign keys stay valid.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass


def _reset_db_connections() -> None:
    import relocation_jobs.db as db_module

    if db_module._sqlite_conn is not None:
        db_module._sqlite_conn.close()
    if db_module._pg_conn is not None and not db_module._pg_conn.closed:
        db_module._pg_conn.close()
    db_module._sqlite_conn = None
    db_module._pg_conn = None
    db_module.reset_db_initialized()


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _pg_columns(conn, table: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row["column_name"])
        else:
            out.append(row[0])
    return out


def _row_to_dict(row) -> dict:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if isinstance(row, dict):
        return row
    return dict(row)


def _pg_has_data(conn) -> bool:
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(_row_to_dict(row).get("n") or 0) > 0


def _truncate_postgres(conn) -> None:
    tables = (
        "fetch_runs",
        "job_status_events",
        "job_tracking",
        "company_tracking",
        "matching_jobs",
        "companies",
        "country_meta",
        "users",
    )
    for table in tables:
        conn.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")


def _copy_table(
    sqlite: sqlite3.Connection,
    pg,
    table: str,
    *,
    skip_columns: frozenset[str] = frozenset(),
) -> int:
    src_cols = [c for c in _sqlite_columns(sqlite, table) if c not in skip_columns]
    dst_cols = set(_pg_columns(pg, table))
    cols = [c for c in src_cols if c in dst_cols]
    if not cols:
        return 0

    rows = sqlite.execute(
        f"SELECT {', '.join(cols)} FROM {table}"
    ).fetchall()
    if not rows:
        return 0

    placeholders = ", ".join("%s" for _ in cols)
    col_list = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    params = [tuple(row[c] for c in cols) for row in rows]
    with pg.cursor() as cur:
        cur.executemany(sql, params)
    return len(params)


def _reset_serial(conn, table: str, column: str = "id") -> None:
    conn.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', '{column}'),
            COALESCE((SELECT MAX({column}) FROM {table}), 1)
        )
        """
    )


def migrate(*, sqlite_path: Path, force: bool) -> dict[str, int]:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is not set. Add your Neon connection string to .env "
            "(postgresql://...?sslmode=require)."
        )

    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    _reset_db_connections()

    from relocation_jobs.db import init_db, get_connection

    init_db(migrate_json=False)
    pg = get_connection()

    if _pg_has_data(pg):
        if not force:
            raise SystemExit(
                "Postgres already has users. Use --force to truncate and re-copy, "
                "or use a fresh Neon database."
            )
        print("Truncating existing Postgres data (--force)…")
        _truncate_postgres(pg)
        pg.commit()

    sqlite = sqlite3.connect(sqlite_path)
    sqlite.row_factory = sqlite3.Row

    counts: dict[str, int] = {}
    order = (
        "users",
        "country_meta",
        "companies",
        "matching_jobs",
        "job_tracking",
        "company_tracking",
        "job_status_events",
        "fetch_runs",
    )
    skip = {"last_fetched"}  # legacy SQLite-only column

    for table in order:
        n = _copy_table(sqlite, pg, table, skip_columns=skip)
        counts[table] = n
        print(f"  {table}: {n} row(s)")

    _reset_serial(pg, "users")
    _reset_serial(pg, "companies")
    _reset_serial(pg, "matching_jobs")
    _reset_serial(pg, "job_status_events")
    _reset_serial(pg, "fetch_runs")
    pg.commit()
    sqlite.close()
    return counts


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=PROJECT_ROOT / "data" / "panel.db",
        help="Path to source SQLite file (default: data/panel.db)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Truncate Postgres tables before copying",
    )
    args = parser.parse_args()

    print(f"Source: {args.sqlite}")
    print(f"Target: Neon/Postgres (DATABASE_URL)")
    counts = migrate(sqlite_path=args.sqlite, force=args.force)
    total = sum(counts.values())
    print(f"Done — copied {total} row(s). Restart the panel server to use Neon.")


if __name__ == "__main__":
    main()
