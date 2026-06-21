"""SQLite or Postgres storage for auth and per-user job tracking."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from relocation_jobs.db_backend import use_postgres
from relocation_jobs.job_identity import job_idempotency_key, normalize_job_url
from relocation_jobs.paths import data_dir

DEFAULT_DB_PATH = data_dir() / "panel.db"

_db_lock = threading.RLock()
_sqlite_conn: sqlite3.Connection | None = None
_pg_conn = None


def db_path() -> Path:
    raw = os.environ.get("PANEL_DB_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_DB_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _configure_sqlite(conn: sqlite3.Connection) -> None:
    """Tune SQLite for concurrent reads during bulk catalog writes (WAL + fast commits)."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")


def _connect_sqlite() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _configure_sqlite(conn)
    return conn


def _connect_postgres():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
    )


def get_connection():
    global _sqlite_conn, _pg_conn
    if use_postgres():
        if _pg_conn is None or _pg_conn.closed:
            _pg_conn = _connect_postgres()
        return _pg_conn
    if _sqlite_conn is None:
        _sqlite_conn = _connect_sqlite()
    return _sqlite_conn


@contextmanager
def db_read():
    """Serialize catalog reads with writes on the shared DB connection."""
    with _db_lock:
        yield get_connection()


@contextmanager
def db_transaction():
    with _db_lock:
        conn = get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def _migrate_schema(conn) -> None:
    """Add columns introduced after initial deploy."""
    if use_postgres():
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS rejected INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS rejected_date TEXT"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS job_title TEXT"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS ats_score INTEGER"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS not_for_me_reason TEXT"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS waiting_referral INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS waiting_referral_date TEXT"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS referral_linkedin_url TEXT"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS seen INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS seen_date TEXT"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS looking_to_apply INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS looking_to_apply_date TEXT"
        )
        _ensure_status_events_table(conn)
        _backfill_job_status_events(conn)
        _migrate_company_tracking_schema(conn)
        _ensure_fetch_runs_table(conn)
        _ensure_users_admin_column(conn)
        return

    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(job_tracking)").fetchall()
    }
    if "rejected" not in cols:
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN rejected INTEGER NOT NULL DEFAULT 0"
        )
    if "rejected_date" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN rejected_date TEXT")
    if "job_title" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN job_title TEXT")
    if "ats_score" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN ats_score INTEGER")
    if "not_for_me_reason" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN not_for_me_reason TEXT")
    if "waiting_referral" not in cols:
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN waiting_referral INTEGER NOT NULL DEFAULT 0"
        )
    if "waiting_referral_date" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN waiting_referral_date TEXT")
    if "referral_linkedin_url" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN referral_linkedin_url TEXT")
    if "seen" not in cols:
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN seen INTEGER NOT NULL DEFAULT 0"
        )
    if "seen_date" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN seen_date TEXT")
    if "looking_to_apply" not in cols:
        conn.execute(
            "ALTER TABLE job_tracking ADD COLUMN looking_to_apply INTEGER NOT NULL DEFAULT 0"
        )
    if "looking_to_apply_date" not in cols:
        conn.execute("ALTER TABLE job_tracking ADD COLUMN looking_to_apply_date TEXT")
    _ensure_status_events_table(conn)
    _backfill_job_status_events(conn)
    _migrate_company_tracking_schema(conn)
    _ensure_fetch_runs_table(conn)
    _ensure_users_admin_column(conn)


def _ensure_users_admin_column(conn) -> None:
    if use_postgres():
        conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin INTEGER NOT NULL DEFAULT 0"
        )
    else:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "is_admin" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )
    admin_name = os.environ.get("PANEL_ADMIN_USER", "admin").strip().lower() or "admin"
    if use_postgres():
        conn.execute(
            "UPDATE users SET is_admin = 1 WHERE LOWER(username) = LOWER(%s)",
            (admin_name,),
        )
    else:
        conn.execute(
            "UPDATE users SET is_admin = 1 WHERE username = ? COLLATE NOCASE",
            (admin_name,),
        )


def _ensure_fetch_runs_table(conn) -> None:
    if use_postgres():
        conn.execute(
            """
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
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fetch_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
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
            result_line TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_fetch_runs_user_started
            ON fetch_runs(user_id, started_at DESC);
        """
    )


def _migrate_company_tracking_schema(conn) -> None:
    if use_postgres():
        conn.execute(
            """
            ALTER TABLE company_tracking
            ADD COLUMN IF NOT EXISTS awaiting_response INTEGER NOT NULL DEFAULT 0
            """
        )
        conn.execute(
            """
            ALTER TABLE company_tracking
            ADD COLUMN IF NOT EXISTS awaiting_response_date TEXT
            """
        )
        return

    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(company_tracking)").fetchall()
    }
    if "awaiting_response" not in cols:
        conn.execute(
            """
            ALTER TABLE company_tracking
            ADD COLUMN awaiting_response INTEGER NOT NULL DEFAULT 0
            """
        )
    if "awaiting_response_date" not in cols:
        conn.execute(
            "ALTER TABLE company_tracking ADD COLUMN awaiting_response_date TEXT"
        )


def _ensure_status_events_table(conn) -> None:
    if use_postgres():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_status_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                country TEXT NOT NULL,
                company_name TEXT NOT NULL,
                job_url TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN ('applied', 'rejected')),
                event_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_job_status_events_user
                ON job_status_events(user_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_job_status_events_job
                ON job_status_events(user_id, country, company_name, job_url)
            """
        )
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_status_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            country TEXT NOT NULL,
            company_name TEXT NOT NULL,
            job_url TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('applied', 'rejected')),
            event_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_job_status_events_user
            ON job_status_events(user_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_job_status_events_job
            ON job_status_events(user_id, country, company_name, job_url)
        """
    )


def _backfill_job_status_events(conn) -> None:
    """Seed history rows from legacy single applied_date / rejected_date columns."""
    ph = "%s" if use_postgres() else "?"
    rows = conn.execute(
        f"""
        SELECT user_id, country, company_name, job_url, applied, applied_date,
               rejected, rejected_date
        FROM job_tracking
        WHERE applied = 1 OR rejected = 1
        """
    ).fetchall()
    now = _utc_now()
    for row in rows:
        data = _row_to_dict(row)
        user_id = data["user_id"]
        country = data["country"]
        company_name = data["company_name"]
        job_url = _normalize_url(data.get("job_url", ""))
        if not job_url:
            continue
        if data.get("applied") and (data.get("applied_date") or "").strip():
            exists = conn.execute(
                f"""
                SELECT 1 FROM job_status_events
                WHERE user_id = {ph} AND country = {ph} AND company_name = {ph}
                  AND job_url = {ph} AND event_type = 'applied'
                LIMIT 1
                """,
                (user_id, country, company_name, job_url),
            ).fetchone()
            if not exists:
                conn.execute(
                    f"""
                    INSERT INTO job_status_events (
                        user_id, country, company_name, job_url,
                        event_type, event_date, created_at
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, 'applied', {ph}, {ph})
                    """,
                    (
                        user_id,
                        country,
                        company_name,
                        job_url,
                        (data.get("applied_date") or "").strip(),
                        now,
                    ),
                )
        if data.get("rejected") and (data.get("rejected_date") or "").strip():
            exists = conn.execute(
                f"""
                SELECT 1 FROM job_status_events
                WHERE user_id = {ph} AND country = {ph} AND company_name = {ph}
                  AND job_url = {ph} AND event_type = 'rejected'
                LIMIT 1
                """,
                (user_id, country, company_name, job_url),
            ).fetchone()
            if not exists:
                conn.execute(
                    f"""
                    INSERT INTO job_status_events (
                        user_id, country, company_name, job_url,
                        event_type, event_date, created_at
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, 'rejected', {ph}, {ph})
                    """,
                    (
                        user_id,
                        country,
                        company_name,
                        job_url,
                        (data.get("rejected_date") or "").strip(),
                        now,
                    ),
                )


def _append_job_status_event(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    event_type: str,
    *,
    event_date: str | None = None,
) -> None:
    job_url = _normalize_url(job_url)
    if not job_url or event_type not in ("applied", "rejected"):
        return
    date_only = (event_date or _utc_now())[:10]
    now = _utc_now()
    ph = "%s" if use_postgres() else "?"
    conn.execute(
        f"""
        INSERT INTO job_status_events (
            user_id, country, company_name, job_url,
            event_type, event_date, created_at
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """,
        (user_id, country, company_name, job_url, event_type, date_only, now),
    )


def _load_status_history_for_job(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> dict[str, list]:
    job_url = _normalize_url(job_url)
    ph = "%s" if use_postgres() else "?"
    rows = conn.execute(
        f"""
        SELECT event_type, event_date, created_at
        FROM job_status_events
        WHERE user_id = {ph} AND country = {ph} AND company_name = {ph} AND job_url = {ph}
        ORDER BY event_date ASC, id ASC
        """,
        (user_id, country, company_name, job_url),
    ).fetchall()
    out: dict[str, list] = {
        "applied": [],
        "rejected": [],
        "applied_events": [],
        "rejected_events": [],
    }
    for row in rows:
        data = _row_to_dict(row)
        event_type = data.get("event_type", "")
        event_date = (data.get("event_date") or "").strip()
        created_at = (data.get("created_at") or "").strip()
        if event_type not in ("applied", "rejected") or not event_date:
            continue
        out[event_type].append(event_date)
        event_key = f"{event_type}_events"
        out[event_key].append({"date": event_date, "at": created_at})
    return out


def load_job_status_history(user_id: int) -> dict[tuple[str, str, str], dict[str, list]]:
    """All apply/reject events keyed by (country, company, normalized job_url)."""
    ph = "%s" if use_postgres() else "?"
    rows = get_connection().execute(
        f"""
        SELECT country, company_name, job_url, event_type, event_date, created_at
        FROM job_status_events
        WHERE user_id = {ph}
        ORDER BY event_date ASC, id ASC
        """,
        (user_id,),
    ).fetchall()
    out: dict[tuple[str, str, str], dict[str, list]] = {}
    for row in rows:
        data = _row_to_dict(row)
        key = (data["country"], data["company_name"], _normalize_url(data.get("job_url", "")))
        if not key[2]:
            continue
        bucket = out.setdefault(
            key,
            {"applied": [], "rejected": [], "applied_events": [], "rejected_events": []},
        )
        event_type = data.get("event_type", "")
        event_date = (data.get("event_date") or "").strip()
        created_at = (data.get("created_at") or "").strip()
        if event_type not in ("applied", "rejected") or not event_date:
            continue
        bucket[event_type].append(event_date)
        bucket[f"{event_type}_events"].append({"date": event_date, "at": created_at})
    return out


def init_db() -> None:
    from relocation_jobs.catalog_db import init_catalog_schema, migrate_from_json_files

    init_catalog_schema()
    with db_transaction() as conn:
        if use_postgres():
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
        else:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_tracking (
                    user_id INTEGER NOT NULL,
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
                    PRIMARY KEY (user_id, country, company_name, job_url),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS company_tracking (
                    user_id INTEGER NOT NULL,
                    country TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    company_applied INTEGER NOT NULL DEFAULT 0,
                    company_applied_date TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, country, company_name),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_job_tracking_user
                    ON job_tracking(user_id);
                CREATE INDEX IF NOT EXISTS idx_company_tracking_user
                    ON company_tracking(user_id);

                CREATE TABLE IF NOT EXISTS fetch_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
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
                    result_line TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_fetch_runs_user_started
                    ON fetch_runs(user_id, started_at DESC);
                """
            )
        _migrate_schema(conn)
    migrate_from_json_files()


def user_count() -> int:
    row = get_connection().execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(_row_to_dict(row).get("n", 0))


def create_user(username: str, password_hash: str, *, is_admin: bool = False) -> dict:
    username = username.strip()
    if not username:
        raise ValueError("Username is required")
    now = _utc_now()
    admin_flag = 1 if is_admin else 0
    with db_transaction() as conn:
        if use_postgres():
            row = conn.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (username, password_hash, now, admin_flag),
            ).fetchone()
            user_id = int(_row_to_dict(row)["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin)
                VALUES (?, ?, ?, ?)
                """,
                (username, password_hash, now, admin_flag),
            )
            user_id = cur.lastrowid
    return {
        "id": user_id,
        "username": username,
        "created_at": now,
        "is_admin": bool(is_admin),
    }


def get_user_by_username(username: str) -> dict | None:
    if use_postgres():
        row = get_connection().execute(
            """
            SELECT id, username, password_hash, created_at
            FROM users WHERE LOWER(username) = LOWER(%s)
            """,
            (username.strip(),),
        ).fetchone()
    else:
        row = get_connection().execute(
            """
            SELECT id, username, password_hash, created_at
            FROM users WHERE username = ? COLLATE NOCASE
            """,
            (username.strip(),),
        ).fetchone()
    return _row_to_dict(row) or None


def get_user_by_id(user_id: int) -> dict | None:
    ph = "%s" if use_postgres() else "?"
    conn = get_connection()
    try:
        row = conn.execute(
            f"SELECT id, username, created_at, is_admin FROM users WHERE id = {ph}",
            (user_id,),
        ).fetchone()
    except Exception as exc:
        if "is_admin" not in str(exc).lower():
            raise
        with db_transaction() as migrate_conn:
            _ensure_users_admin_column(migrate_conn)
        row = conn.execute(
            f"SELECT id, username, created_at, is_admin FROM users WHERE id = {ph}",
            (user_id,),
        ).fetchone()
    data = _row_to_dict(row)
    if not data:
        return None
    data["is_admin"] = bool(data.get("is_admin"))
    return data


def is_user_admin(user_id: int) -> bool:
    user = get_user_by_id(user_id)
    if not user:
        return False
    if user.get("is_admin"):
        return True
    admin_name = os.environ.get("PANEL_ADMIN_USER", "admin").strip().lower() or "admin"
    return user.get("username", "").strip().lower() == admin_name


def list_users_with_stats() -> list[dict]:
    sql = """
        SELECT
            u.id,
            u.username,
            u.created_at,
            u.is_admin,
            (SELECT COUNT(*) FROM job_tracking j WHERE j.user_id = u.id) AS tracking_rows,
            (SELECT COUNT(*) FROM job_tracking j WHERE j.user_id = u.id AND j.applied = 1)
                AS applied_positions,
            (SELECT COUNT(*) FROM job_tracking j WHERE j.user_id = u.id AND j.rejected = 1)
                AS rejected_positions,
            (SELECT COUNT(*) FROM job_tracking j WHERE j.user_id = u.id AND j.not_for_me = 1)
                AS not_for_me_positions,
            (SELECT COUNT(*) FROM fetch_runs f WHERE f.user_id = u.id) AS fetch_runs
        FROM users u
        ORDER BY u.created_at ASC, u.id ASC
    """
    conn = get_connection()
    try:
        rows = conn.execute(sql).fetchall()
    except Exception as exc:
        if "is_admin" not in str(exc).lower():
            raise
        with db_transaction() as migrate_conn:
            _ensure_users_admin_column(migrate_conn)
        rows = conn.execute(sql).fetchall()
    out: list[dict] = []
    admin_name = os.environ.get("PANEL_ADMIN_USER", "admin").strip().lower() or "admin"
    for row in rows:
        data = _row_to_dict(row)
        username = (data.get("username") or "").strip()
        out.append(
            {
                "id": data["id"],
                "username": username,
                "created_at": data.get("created_at"),
                "is_admin": bool(data.get("is_admin"))
                or username.lower() == admin_name,
                "tracking_rows": int(data.get("tracking_rows") or 0),
                "applied_positions": int(data.get("applied_positions") or 0),
                "rejected_positions": int(data.get("rejected_positions") or 0),
                "not_for_me_positions": int(data.get("not_for_me_positions") or 0),
                "fetch_runs": int(data.get("fetch_runs") or 0),
            }
        )
    return out


def admin_tracking_totals() -> dict:
    row = get_connection().execute(
        """
        SELECT
            COUNT(*) AS tracking_rows,
            COALESCE(SUM(applied), 0) AS applied_positions,
            COALESCE(SUM(rejected), 0) AS rejected_positions,
            COALESCE(SUM(not_for_me), 0) AS not_for_me_positions
        FROM job_tracking
        """
    ).fetchone()
    data = _row_to_dict(row)
    return {
        "tracking_rows": int(data.get("tracking_rows") or 0),
        "applied_positions": int(data.get("applied_positions") or 0),
        "rejected_positions": int(data.get("rejected_positions") or 0),
        "not_for_me_positions": int(data.get("not_for_me_positions") or 0),
    }


def update_user_password(username: str, password_hash: str) -> bool:
    with db_transaction() as conn:
        if use_postgres():
            cur = conn.execute(
                "UPDATE users SET password_hash = %s WHERE LOWER(username) = LOWER(%s)",
                (password_hash, username.strip()),
            )
        else:
            cur = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ? COLLATE NOCASE",
                (password_hash, username.strip()),
            )
        return cur.rowcount > 0


def rename_user(user_id: int, username: str) -> bool:
    username = username.strip()
    ph = "%s" if use_postgres() else "?"
    with db_transaction() as conn:
        cur = conn.execute(
            f"UPDATE users SET username = {ph} WHERE id = {ph}",
            (username, user_id),
        )
        return cur.rowcount > 0


def _normalize_url(url: str) -> str:
    return normalize_job_url(url)


def _resolve_tracking_url(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> str:
    """Return the tracking row URL for this job (exact or idempotency alias)."""
    job_url = _normalize_url(job_url)
    job_key = job_idempotency_key(job_url)
    if not job_key:
        return job_url
    ph = "%s" if use_postgres() else "?"
    rows = conn.execute(
        f"""
        SELECT job_url FROM job_tracking
        WHERE user_id = {ph} AND country = {ph} AND company_name = {ph}
        """,
        (user_id, country, company_name),
    ).fetchall()
    alias = job_url
    for row in rows:
        stored = _normalize_url(_row_to_dict(row).get("job_url", ""))
        if stored == job_url:
            return job_url
        if job_idempotency_key(stored) == job_key:
            alias = stored
    return alias


def _tracking_urls_for_job(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> set[str]:
    """All tracking URLs that refer to the same job (normalized + idempotency aliases)."""
    canonical_url = _normalize_url(job_url)
    urls = {canonical_url}
    job_key = job_idempotency_key(canonical_url)
    if not job_key:
        return urls
    ph = "%s" if use_postgres() else "?"
    rows = conn.execute(
        f"""
        SELECT job_url FROM job_tracking
        WHERE user_id = {ph} AND country = {ph} AND company_name = {ph}
        """,
        (user_id, country, company_name),
    ).fetchall()
    for row in rows:
        stored = _normalize_url(_row_to_dict(row).get("job_url", ""))
        if job_idempotency_key(stored) == job_key:
            urls.add(stored)
    return urls


def count_jobs_applied_db(
    user_id: int,
    *,
    country: str | None = None,
) -> int:
    """Count positions currently marked applied for the user."""
    ph = "%s" if use_postgres() else "?"
    conn = get_connection()
    if country:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM job_tracking
            WHERE user_id = {ph} AND applied = 1 AND country = {ph}
            """,
            (user_id, country),
        ).fetchone()
    else:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM job_tracking
            WHERE user_id = {ph} AND applied = 1
            """,
            (user_id,),
        ).fetchone()
    data = _row_to_dict(row)
    return int(data.get("n") or 0)


def _resolve_timezone(name: str | None) -> ZoneInfo:
    tz = (name or "").strip() or "UTC"
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local_day_utc_bounds(tz: ZoneInfo) -> tuple[str, str]:
    """UTC ISO bounds [start, end) for the current calendar day in ``tz``."""
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    end_utc = end_local.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    return start_utc, end_utc


def _applied_today_event_rows(
    conn,
    user_id: int,
    start_utc: str,
    end_utc: str,
    country: str | None,
) -> list:
    """Apply events whose ``created_at`` falls in the user's local calendar day."""
    ph = "%s" if use_postgres() else "?"
    if country:
        return conn.execute(
            f"""
            SELECT e.country, e.company_name, e.job_url, e.event_date, e.created_at,
                   t.job_title
            FROM job_status_events e
            LEFT JOIN job_tracking t
              ON t.user_id = e.user_id AND t.country = e.country
             AND t.company_name = e.company_name AND t.job_url = e.job_url
            WHERE e.user_id = {ph} AND e.event_type = 'applied' AND e.country = {ph}
              AND e.created_at >= {ph} AND e.created_at < {ph}
            ORDER BY e.created_at DESC
            """,
            (user_id, country, start_utc, end_utc),
        ).fetchall()
    return conn.execute(
        f"""
        SELECT e.country, e.company_name, e.job_url, e.event_date, e.created_at,
               t.job_title
        FROM job_status_events e
        LEFT JOIN job_tracking t
          ON t.user_id = e.user_id AND t.country = e.country
         AND t.company_name = e.company_name AND t.job_url = e.job_url
        WHERE e.user_id = {ph} AND e.event_type = 'applied'
          AND e.created_at >= {ph} AND e.created_at < {ph}
        ORDER BY e.created_at DESC
        """,
        (user_id, start_utc, end_utc),
    ).fetchall()


def _jobs_applied_today_from_rows(rows: list) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for row in rows:
        data = _row_to_dict(row)
        url = _normalize_url(data.get("job_url", ""))
        if not url:
            continue
        key = (data["country"], data["company_name"], url)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "country": data["country"],
            "company": data["company_name"],
            "url": url,
            "title": (data.get("job_title") or "").strip(),
            "event_date": (data.get("event_date") or "").strip(),
            "applied_at": (data.get("created_at") or "").strip(),
        })
    return out


def list_jobs_applied_today_db(
    user_id: int,
    *,
    country: str | None = None,
    timezone_name: str | None = None,
) -> list[dict]:
    """Return distinct positions with an apply event during the user's local calendar day."""
    tz = _resolve_timezone(timezone_name)
    start_utc, end_utc = _local_day_utc_bounds(tz)
    conn = get_connection()
    rows = _applied_today_event_rows(conn, user_id, start_utc, end_utc, country)
    return _jobs_applied_today_from_rows(rows)


def count_jobs_applied_today_db(
    user_id: int,
    *,
    country: str | None = None,
    timezone_name: str | None = None,
) -> int:
    """Count distinct positions applied during the user's local calendar day."""
    return len(list_jobs_applied_today_db(
        user_id,
        country=country,
        timezone_name=timezone_name,
    ))


def load_job_tracking(user_id: int) -> dict[tuple[str, str, str], dict]:
    ph = "%s" if use_postgres() else "?"
    rows = get_connection().execute(
        f"""
        SELECT country, company_name, job_url, job_title, ats_score, applied, applied_date,
               not_for_me, not_for_me_date, not_for_me_reason, rejected, rejected_date,
               waiting_referral, waiting_referral_date, referral_linkedin_url,
               seen, seen_date, looking_to_apply, looking_to_apply_date, updated_at
        FROM job_tracking
        WHERE user_id = {ph}
        """,
        (user_id,),
    ).fetchall()
    out: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        data = _row_to_dict(row)
        key = (data["country"], data["company_name"], _normalize_url(data["job_url"]))
        out[key] = data
    return out


def load_company_tracking(user_id: int) -> dict[tuple[str, str], dict]:
    ph = "%s" if use_postgres() else "?"
    rows = get_connection().execute(
        f"""
        SELECT country, company_name, company_applied, company_applied_date,
               awaiting_response, awaiting_response_date
        FROM company_tracking
        WHERE user_id = {ph}
        """,
        (user_id,),
    ).fetchall()
    return {
        (d["country"], d["company_name"]): d
        for row in rows
        for d in [_row_to_dict(row)]
    }


def set_job_applied_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    applied: bool,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    preserved_looking_to_apply_date = ""
    with db_transaction() as conn:
        if applied:
            title = (job_title or "").strip()
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        looking_to_apply, looking_to_apply_date, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 1, %s, 0, NULL, 0, NULL, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        applied = 1,
                        applied_date = EXCLUDED.applied_date,
                        looking_to_apply = 0,
                        job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, now[:10], now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        looking_to_apply, looking_to_apply_date, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, 0, NULL, 0, NULL, ?)
                    ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                        applied = 1,
                        applied_date = excluded.applied_date,
                        looking_to_apply = 0,
                        job_title = COALESCE(NULLIF(excluded.job_title, ''), job_title),
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, now[:10], now),
                )
            applied_date = now[:10]
            _append_job_status_event(
                conn,
                user_id,
                country,
                company_name,
                job_url,
                "applied",
                event_date=applied_date,
            )
            if use_postgres():
                row = conn.execute(
                    """
                    SELECT looking_to_apply_date
                    FROM job_tracking
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (user_id, country, company_name, job_url),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT looking_to_apply_date
                    FROM job_tracking
                    WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                    """,
                    (user_id, country, company_name, job_url),
                ).fetchone()
            preserved_looking_to_apply_date = (row["looking_to_apply_date"] or "") if row else ""
        else:
            if use_postgres():
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET applied = 0, applied_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, job_url),
                )
            else:
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET applied = 0, applied_date = NULL, updated_at = ?
                    WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                    """,
                    (now, user_id, country, company_name, job_url),
                )
            applied_date = ""
    result = {
        "applied": applied,
        "applied_date": applied_date if applied else "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }
    if applied:
        result["looking_to_apply"] = False
        result["looking_to_apply_date"] = preserved_looking_to_apply_date
    with db_transaction() as conn:
        history = _load_status_history_for_job(
            conn, user_id, country, company_name, job_url
        )
    latest_applied = max(history["applied"]) if history["applied"] else ""
    if latest_applied:
        result["applied_date"] = latest_applied
    latest_applied_at = max(
        ((event.get("at") or "").strip() for event in history.get("applied_events") or []),
        default="",
    )
    if latest_applied_at:
        result["applied_at"] = latest_applied_at
    elif applied:
        result["applied_at"] = now
    result["applied_history"] = history["applied"]
    result["applied_events"] = history.get("applied_events") or []
    result["rejected_history"] = history["rejected"]
    return result


def sync_company_applied_from_jobs_db(
    user_id: int,
    country: str,
    company_name: str,
) -> dict:
    """Mirror company-level applied state from position-level applied marks."""
    now = _utc_now()
    with db_transaction() as conn:
        if use_postgres():
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt, MIN(applied_date) AS earliest
                FROM job_tracking
                WHERE user_id = %s AND country = %s AND company_name = %s AND applied = 1
                """,
                (user_id, country, company_name),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt, MIN(applied_date) AS earliest
                FROM job_tracking
                WHERE user_id = ? AND country = ? AND company_name = ? AND applied = 1
                """,
                (user_id, country, company_name),
            ).fetchone()

        count = int(row["cnt"] if row else 0)
        if count > 0:
            applied_date = (row["earliest"] or "").strip() or now[:10]
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO company_tracking (
                        user_id, country, company_name,
                        company_applied, company_applied_date, updated_at
                    ) VALUES (%s, %s, %s, 1, %s, %s)
                    ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                        company_applied = 1,
                        company_applied_date = EXCLUDED.company_applied_date,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, applied_date, now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO company_tracking (
                        user_id, country, company_name,
                        company_applied, company_applied_date, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(user_id, country, company_name) DO UPDATE SET
                        company_applied = 1,
                        company_applied_date = excluded.company_applied_date,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, applied_date, now),
                )
            return {
                "company_applied": True,
                "company_applied_date": applied_date,
                "positions_applied": count,
                "company": company_name,
                "country": country,
            }

        if use_postgres():
            conn.execute(
                """
                UPDATE company_tracking
                SET company_applied = 0, company_applied_date = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s
                """,
                (now, user_id, country, company_name),
            )
        else:
            conn.execute(
                """
                UPDATE company_tracking
                SET company_applied = 0, company_applied_date = NULL, updated_at = ?
                WHERE user_id = ? AND country = ? AND company_name = ?
                """,
                (now, user_id, country, company_name),
            )
    return {
        "company_applied": False,
        "company_applied_date": "",
        "positions_applied": 0,
        "company": company_name,
        "country": country,
    }


def set_job_not_for_me_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    *,
    not_for_me: bool = True,
    reason: str | None = None,
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    date_only = now[:10]
    hide_reason = (reason or "not_for_me").strip() or "not_for_me"
    with db_transaction() as conn:
        if not_for_me:
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url,
                        applied, applied_date, not_for_me, not_for_me_date,
                        not_for_me_reason, updated_at
                    ) VALUES (%s, %s, %s, %s, 0, NULL, 1, %s, %s, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        not_for_me = 1,
                        not_for_me_date = EXCLUDED.not_for_me_date,
                        not_for_me_reason = EXCLUDED.not_for_me_reason,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, job_url, date_only, hide_reason, now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url,
                        applied, applied_date, not_for_me, not_for_me_date,
                        not_for_me_reason, updated_at
                    ) VALUES (?, ?, ?, ?, 0, NULL, 1, ?, ?, ?)
                    ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                        not_for_me = 1,
                        not_for_me_date = excluded.not_for_me_date,
                        not_for_me_reason = excluded.not_for_me_reason,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, job_url, date_only, hide_reason, now),
                )
            return {
                "not_for_me": True,
                "not_for_me_date": date_only,
                "not_for_me_reason": hide_reason,
                "company": company_name,
                "url": job_url,
                "country": country,
            }

        if use_postgres():
            conn.execute(
                """
                UPDATE job_tracking
                SET not_for_me = 0, not_for_me_date = NULL, not_for_me_reason = NULL,
                    updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, job_url),
            )
        else:
            conn.execute(
                """
                UPDATE job_tracking
                SET not_for_me = 0, not_for_me_date = NULL, not_for_me_reason = NULL,
                    updated_at = ?
                WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                """,
                (now, user_id, country, company_name, job_url),
            )
    return {
        "not_for_me": False,
        "not_for_me_date": "",
        "not_for_me_reason": "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_rejected_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    rejected: bool,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        if rejected:
            title = (job_title or "").strip()
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        rejected, rejected_date, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        rejected = 1,
                        rejected_date = EXCLUDED.rejected_date,
                        job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, now[:10], now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        rejected, rejected_date, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0, NULL, 0, NULL, 1, ?, ?)
                    ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                        rejected = 1,
                        rejected_date = excluded.rejected_date,
                        job_title = COALESCE(NULLIF(excluded.job_title, ''), job_title),
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, now[:10], now),
                )
            rejected_date = now[:10]
            _append_job_status_event(
                conn,
                user_id,
                country,
                company_name,
                job_url,
                "rejected",
                event_date=rejected_date,
            )
        else:
            if use_postgres():
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET rejected = 0, rejected_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, job_url),
                )
            else:
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET rejected = 0, rejected_date = NULL, updated_at = ?
                    WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                    """,
                    (now, user_id, country, company_name, job_url),
                )
            rejected_date = ""
    with db_transaction() as conn:
        history = _load_status_history_for_job(
            conn, user_id, country, company_name, job_url
        )
    latest_rejected = max(history["rejected"]) if history["rejected"] else ""
    if latest_rejected:
        result_rejected_date = latest_rejected
    else:
        result_rejected_date = rejected_date if rejected else ""
    latest_applied = max(history["applied"]) if history["applied"] else ""
    return {
        "rejected": rejected,
        "rejected_date": result_rejected_date,
        "applied_date": latest_applied,
        "applied_history": history["applied"],
        "rejected_history": history["rejected"],
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def reapply_job_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> dict:
    """Clear active rejection so the role returns to the main positions list."""
    return set_job_rejected_db(
        user_id,
        country,
        company_name,
        job_url,
        rejected=False,
    )


def set_job_looking_to_apply_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    looking_to_apply: bool,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        if looking_to_apply:
            title = (job_title or "").strip()
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        looking_to_apply, looking_to_apply_date, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        looking_to_apply = 1,
                        looking_to_apply_date = EXCLUDED.looking_to_apply_date,
                        job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, now[:10], now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        looking_to_apply, looking_to_apply_date, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0, NULL, 0, NULL, 1, ?, ?)
                    ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                        looking_to_apply = 1,
                        looking_to_apply_date = excluded.looking_to_apply_date,
                        job_title = COALESCE(NULLIF(excluded.job_title, ''), job_title),
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, now[:10], now),
                )
            looking_to_apply_date = now[:10]
        else:
            if use_postgres():
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET looking_to_apply = 0, looking_to_apply_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, job_url),
                )
            else:
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET looking_to_apply = 0, looking_to_apply_date = NULL, updated_at = ?
                    WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                    """,
                    (now, user_id, country, company_name, job_url),
                )
            looking_to_apply_date = ""
    return {
        "looking_to_apply": looking_to_apply,
        "looking_to_apply_date": looking_to_apply_date if looking_to_apply else "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_seen_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    seen: bool = True,
    *,
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        storage_url = _resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url
        )
        if seen:
            title = (job_title or "").strip()
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        seen, seen_date, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        seen = 1,
                        seen_date = COALESCE(job_tracking.seen_date, EXCLUDED.seen_date),
                        job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, storage_url, title, now[:10], now),
                )
                if storage_url != canonical_url:
                    conn.execute(
                        """
                        INSERT INTO job_tracking (
                            user_id, country, company_name, job_url, job_title,
                            applied, applied_date, not_for_me, not_for_me_date,
                            seen, seen_date, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                        ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                            seen = 1,
                            seen_date = COALESCE(job_tracking.seen_date, EXCLUDED.seen_date),
                            job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                            updated_at = EXCLUDED.updated_at
                        """,
                        (user_id, country, company_name, canonical_url, title, now[:10], now),
                    )
                row = conn.execute(
                    "SELECT seen_date FROM job_tracking WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s",
                    (user_id, country, company_name, canonical_url),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT seen_date FROM job_tracking WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s",
                        (user_id, country, company_name, storage_url),
                    ).fetchone()
            else:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        seen, seen_date, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0, NULL, 0, NULL, 1, ?, ?)
                    ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                        seen = 1,
                        seen_date = COALESCE(seen_date, excluded.seen_date),
                        job_title = COALESCE(NULLIF(excluded.job_title, ''), job_title),
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, storage_url, title, now[:10], now),
                )
                if storage_url != canonical_url:
                    conn.execute(
                        """
                        INSERT INTO job_tracking (
                            user_id, country, company_name, job_url, job_title,
                            applied, applied_date, not_for_me, not_for_me_date,
                            seen, seen_date, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 0, NULL, 0, NULL, 1, ?, ?)
                        ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                            seen = 1,
                            seen_date = COALESCE(seen_date, excluded.seen_date),
                            job_title = COALESCE(NULLIF(excluded.job_title, ''), job_title),
                            updated_at = excluded.updated_at
                        """,
                        (user_id, country, company_name, canonical_url, title, now[:10], now),
                    )
                row = conn.execute(
                    "SELECT seen_date FROM job_tracking WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?",
                    (user_id, country, company_name, canonical_url),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT seen_date FROM job_tracking WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?",
                        (user_id, country, company_name, storage_url),
                    ).fetchone()
            seen_date = (row["seen_date"] if row else None) or now[:10]
        else:
            urls_to_clear = _tracking_urls_for_job(
                conn, user_id, country, company_name, canonical_url
            )
            if use_postgres():
                for url in urls_to_clear:
                    conn.execute(
                        """
                        UPDATE job_tracking
                        SET seen = 0, seen_date = NULL, updated_at = %s
                        WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                        """,
                        (now, user_id, country, company_name, url),
                    )
            else:
                for url in urls_to_clear:
                    conn.execute(
                        """
                        UPDATE job_tracking
                        SET seen = 0, seen_date = NULL, updated_at = ?
                        WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                        """,
                        (now, user_id, country, company_name, url),
                    )
            seen_date = ""
    return {
        "seen": seen,
        "seen_date": seen_date if seen else "",
        "idempotency_key": job_idempotency_key(canonical_url),
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_waiting_referral_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    waiting_referral: bool,
    *,
    linkedin_url: str = "",
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    date_only = now[:10]
    linkedin = (linkedin_url or "").strip()
    with db_transaction() as conn:
        if waiting_referral:
            if not linkedin:
                raise ValueError("LinkedIn profile URL is required")
            title = (job_title or "").strip()
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        waiting_referral, waiting_referral_date, referral_linkedin_url,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        waiting_referral = 1,
                        waiting_referral_date = EXCLUDED.waiting_referral_date,
                        referral_linkedin_url = EXCLUDED.referral_linkedin_url,
                        job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, date_only, linkedin, now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        waiting_referral, waiting_referral_date, referral_linkedin_url,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0, NULL, 0, NULL, 1, ?, ?, ?)
                    ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                        waiting_referral = 1,
                        waiting_referral_date = excluded.waiting_referral_date,
                        referral_linkedin_url = excluded.referral_linkedin_url,
                        job_title = COALESCE(NULLIF(excluded.job_title, ''), job_title),
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, date_only, linkedin, now),
                )
            return {
                "waiting_referral": True,
                "waiting_referral_date": date_only,
                "referral_linkedin_url": linkedin,
                "company": company_name,
                "url": job_url,
                "country": country,
            }

        if use_postgres():
            conn.execute(
                """
                UPDATE job_tracking
                SET waiting_referral = 0, waiting_referral_date = NULL,
                    referral_linkedin_url = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, job_url),
            )
        else:
            conn.execute(
                """
                UPDATE job_tracking
                SET waiting_referral = 0, waiting_referral_date = NULL,
                    referral_linkedin_url = NULL, updated_at = ?
                WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                """,
                (now, user_id, country, company_name, job_url),
            )
    return {
        "waiting_referral": False,
        "waiting_referral_date": "",
        "referral_linkedin_url": "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_ats_score_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    ats_score: int | None,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    title = (job_title or "").strip()
    with db_transaction() as conn:
        if ats_score is not None:
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title, ats_score,
                        applied, applied_date, not_for_me, not_for_me_date,
                        rejected, rejected_date, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 0, NULL, 0, NULL, 0, NULL, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        ats_score = EXCLUDED.ats_score,
                        job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, ats_score, now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title, ats_score,
                        applied, applied_date, not_for_me, not_for_me_date,
                        rejected, rejected_date, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, 0, NULL, 0, NULL, ?)
                    ON CONFLICT(user_id, country, company_name, job_url) DO UPDATE SET
                        ats_score = excluded.ats_score,
                        job_title = COALESCE(NULLIF(excluded.job_title, ''), job_title),
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, job_url, title, ats_score, now),
                )
        elif use_postgres():
            conn.execute(
                """
                UPDATE job_tracking
                SET ats_score = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, job_url),
            )
        else:
            conn.execute(
                """
                UPDATE job_tracking
                SET ats_score = NULL, updated_at = ?
                WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?
                """,
                (now, user_id, country, company_name, job_url),
            )
    return {
        "ats_score": ats_score,
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_company_applied_db(
    user_id: int,
    country: str,
    company_name: str,
    applied: bool,
) -> dict:
    now = _utc_now()
    with db_transaction() as conn:
        if applied:
            if use_postgres():
                conn.execute(
                    """
                    INSERT INTO company_tracking (
                        user_id, country, company_name,
                        company_applied, company_applied_date, updated_at
                    ) VALUES (%s, %s, %s, 1, %s, %s)
                    ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                        company_applied = 1,
                        company_applied_date = EXCLUDED.company_applied_date,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, now[:10], now),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO company_tracking (
                        user_id, country, company_name,
                        company_applied, company_applied_date, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(user_id, country, company_name) DO UPDATE SET
                        company_applied = 1,
                        company_applied_date = excluded.company_applied_date,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, now[:10], now),
                )
            applied_date = now[:10]
        else:
            if use_postgres():
                conn.execute(
                    """
                    UPDATE company_tracking
                    SET company_applied = 0, company_applied_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s
                    """,
                    (now, user_id, country, company_name),
                )
            else:
                conn.execute(
                    """
                    UPDATE company_tracking
                    SET company_applied = 0, company_applied_date = NULL, updated_at = ?
                    WHERE user_id = ? AND country = ? AND company_name = ?
                    """,
                    (now, user_id, country, company_name),
                )
            applied_date = ""
    return {
        "company_applied": applied,
        "company_applied_date": applied_date if applied else "",
        "company": company_name,
        "country": country,
    }


def set_company_awaiting_response_db(
    user_id: int,
    country: str,
    company_name: str,
    awaiting: bool,
    *,
    preserve_date: bool = False,
) -> dict:
    """Mark company as waiting on application response(s) before applying elsewhere."""
    now = _utc_now()
    with db_transaction() as conn:
        if awaiting:
            date_only = now[:10]
            if preserve_date:
                date_update_pg = (
                    "awaiting_response_date = COALESCE("
                    "company_tracking.awaiting_response_date, EXCLUDED.awaiting_response_date)"
                )
                date_update_sql = (
                    "awaiting_response_date = COALESCE("
                    "awaiting_response_date, excluded.awaiting_response_date)"
                )
            else:
                date_update_pg = "awaiting_response_date = EXCLUDED.awaiting_response_date"
                date_update_sql = "awaiting_response_date = excluded.awaiting_response_date"
            if use_postgres():
                conn.execute(
                    f"""
                    INSERT INTO company_tracking (
                        user_id, country, company_name,
                        awaiting_response, awaiting_response_date, updated_at
                    ) VALUES (%s, %s, %s, 1, %s, %s)
                    ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                        awaiting_response = 1,
                        {date_update_pg},
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, date_only, now),
                )
            else:
                conn.execute(
                    f"""
                    INSERT INTO company_tracking (
                        user_id, country, company_name,
                        awaiting_response, awaiting_response_date, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(user_id, country, company_name) DO UPDATE SET
                        awaiting_response = 1,
                        {date_update_sql},
                        updated_at = excluded.updated_at
                    """,
                    (user_id, country, company_name, date_only, now),
                )
            ph = "%s" if use_postgres() else "?"
            row = conn.execute(
                f"""
                SELECT awaiting_response_date FROM company_tracking
                WHERE user_id = {ph} AND country = {ph} AND company_name = {ph}
                """,
                (user_id, country, company_name),
            ).fetchone()
            awaiting_date = (_row_to_dict(row).get("awaiting_response_date") or date_only)
        else:
            if use_postgres():
                conn.execute(
                    """
                    UPDATE company_tracking
                    SET awaiting_response = 0, awaiting_response_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s
                    """,
                    (now, user_id, country, company_name),
                )
            else:
                conn.execute(
                    """
                    UPDATE company_tracking
                    SET awaiting_response = 0, awaiting_response_date = NULL, updated_at = ?
                    WHERE user_id = ? AND country = ? AND company_name = ?
                    """,
                    (now, user_id, country, company_name),
                )
            awaiting_date = ""
    return {
        "awaiting_response": awaiting,
        "awaiting_response_date": awaiting_date if awaiting else "",
        "company": company_name,
        "country": country,
    }


def tracking_is_empty() -> bool:
    row = get_connection().execute(
        """
        SELECT (SELECT COUNT(*) FROM job_tracking)
             + (SELECT COUNT(*) FROM company_tracking) AS n
        """
    ).fetchone()
    return int(_row_to_dict(row).get("n", 0)) == 0


def migrate_tracking_from_json(user_id: int) -> int:
    from relocation_jobs.catalog_db import load_country as load_country_catalog
    from relocation_jobs.panel_data import COUNTRY_FILES

    written = 0
    with db_transaction() as conn:
        for country_key, filename in COUNTRY_FILES.items():
            data = load_country_catalog(country_key)
            if data is None:
                continue
            for company in data.get("companies", []):
                name = company.get("name", "")
                if not name:
                    continue
                if company.get("company_applied"):
                    if use_postgres():
                        conn.execute(
                            """
                            INSERT INTO company_tracking (
                                user_id, country, company_name,
                                company_applied, company_applied_date, updated_at
                            ) VALUES (%s, %s, %s, 1, %s, %s)
                            ON CONFLICT (user_id, country, company_name) DO NOTHING
                            """,
                            (
                                user_id,
                                country_key,
                                name,
                                company.get("company_applied_date") or _utc_now()[:10],
                                _utc_now(),
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO company_tracking (
                                user_id, country, company_name,
                                company_applied, company_applied_date, updated_at
                            ) VALUES (?, ?, ?, 1, ?, ?)
                            ON CONFLICT(user_id, country, company_name) DO NOTHING
                            """,
                            (
                                user_id,
                                country_key,
                                name,
                                company.get("company_applied_date") or _utc_now()[:10],
                                _utc_now(),
                            ),
                        )
                    written += 1

                for job in company.get("matching_jobs") or []:
                    url = _normalize_url(job.get("url", ""))
                    if not url:
                        continue
                    applied = bool(job.get("applied"))
                    not_for_me = bool(job.get("not_for_me"))
                    rejected = bool(job.get("rejected"))
                    if not applied and not not_for_me and not rejected:
                        continue
                    params = (
                        user_id,
                        country_key,
                        name,
                        url,
                        1 if applied else 0,
                        job.get("applied_date") if applied else None,
                        1 if not_for_me else 0,
                        job.get("not_for_me_date") if not_for_me else None,
                        1 if rejected else 0,
                        job.get("rejected_date") if rejected else None,
                        _utc_now(),
                    )
                    if use_postgres():
                        conn.execute(
                            """
                            INSERT INTO job_tracking (
                                user_id, country, company_name, job_url,
                                applied, applied_date, not_for_me, not_for_me_date,
                                rejected, rejected_date, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (user_id, country, company_name, job_url) DO NOTHING
                            """,
                            params,
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO job_tracking (
                                user_id, country, company_name, job_url,
                                applied, applied_date, not_for_me, not_for_me_date,
                                rejected, rejected_date, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(user_id, country, company_name, job_url) DO NOTHING
                            """,
                            params,
                        )
                    written += 1
    return written


def _duration_seconds(started_at: str, finished_at: str) -> float | None:
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
        return max(0.0, (finish - start).total_seconds())
    except (ValueError, TypeError):
        return None


def _fetch_run_to_dict(row) -> dict:
    data = _row_to_dict(row)
    if not data:
        return {}
    company_name = (data.get("company_name") or "").strip() or None
    scope = (data.get("scope") or "").strip() or ("company" if company_name else "country")
    duration = data.get("duration_seconds")
    if duration is None:
        duration = _duration_seconds(data.get("started_at", ""), data.get("finished_at", ""))
    return {
        "id": data.get("id"),
        "user_id": data.get("user_id"),
        "country": data.get("country"),
        "company_name": company_name,
        "scope": scope,
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "duration_seconds": duration,
        "exit_code": data.get("exit_code"),
        "cancelled": bool(data.get("cancelled")),
        "new_jobs": int(data.get("new_jobs") or 0),
        "concurrency": data.get("concurrency"),
        "companies_done": data.get("companies_done"),
        "companies_total": data.get("companies_total"),
        "result_line": data.get("result_line"),
    }


def record_fetch_run(
    *,
    user_id: int,
    country: str,
    company_name: str | None,
    started_at: str,
    finished_at: str,
    exit_code: int | None,
    cancelled: bool = False,
    new_jobs: int = 0,
    concurrency: int | None = None,
    companies_done: int | None = None,
    companies_total: int | None = None,
    result_line: str | None = None,
) -> dict:
    company_name = (company_name or "").strip() or None
    scope = "company" if company_name else "country"
    duration = _duration_seconds(started_at, finished_at)
    params = (
        int(user_id),
        country,
        company_name,
        scope,
        started_at,
        finished_at,
        duration,
        exit_code,
        1 if cancelled else 0,
        int(new_jobs or 0),
        concurrency,
        companies_done,
        companies_total,
        (result_line or "").strip() or None,
    )
    with db_transaction() as conn:
        if use_postgres():
            row = conn.execute(
                """
                INSERT INTO fetch_runs (
                    user_id, country, company_name, scope,
                    started_at, finished_at, duration_seconds,
                    exit_code, cancelled, new_jobs, concurrency,
                    companies_done, companies_total, result_line
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                params,
            ).fetchone()
        else:
            conn.execute(
                """
                INSERT INTO fetch_runs (
                    user_id, country, company_name, scope,
                    started_at, finished_at, duration_seconds,
                    exit_code, cancelled, new_jobs, concurrency,
                    companies_done, companies_total, result_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
            row = conn.execute(
                "SELECT * FROM fetch_runs WHERE id = last_insert_rowid()"
            ).fetchone()
    return _fetch_run_to_dict(row)


def list_fetch_runs(
    user_id: int,
    *,
    country: str | None = None,
    limit: int = 20,
) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    ph = "%s" if use_postgres() else "?"
    sql = f"""
        SELECT * FROM fetch_runs
        WHERE user_id = {ph}
    """
    params: list = [int(user_id)]
    if country:
        sql += f" AND country = {ph}"
        params.append(country)
    sql += f" ORDER BY started_at DESC, id DESC LIMIT {ph}"
    params.append(limit)
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    return [_fetch_run_to_dict(row) for row in rows]


def list_all_fetch_runs(
    *,
    country: str | None = None,
    limit: int = 50,
) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    ph = "%s" if use_postgres() else "?"
    sql = f"""
        SELECT f.*, u.username
        FROM fetch_runs f
        JOIN users u ON u.id = f.user_id
        WHERE 1=1
    """
    params: list = []
    if country:
        sql += f" AND f.country = {ph}"
        params.append(country)
    sql += f" ORDER BY f.started_at DESC, f.id DESC LIMIT {ph}"
    params.append(limit)
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    out: list[dict] = []
    for row in rows:
        data = _fetch_run_to_dict(row)
        rd = _row_to_dict(row)
        data["username"] = rd.get("username")
        out.append(data)
    return out


def clear_company_tracking(country: str, company_name: str) -> None:
    """Remove all user tracking rows for a company (after it is deleted from JSON)."""
    from relocation_jobs.db_backend import use_postgres

    ph = "%s" if use_postgres() else "?"
    with db_transaction() as conn:
        conn.execute(
            f"DELETE FROM job_tracking WHERE country = {ph} AND company_name = {ph}",
            (country, company_name),
        )
        conn.execute(
            f"DELETE FROM company_tracking WHERE country = {ph} AND company_name = {ph}",
            (country, company_name),
        )


def rename_company_tracking(country: str, old_name: str, new_name: str) -> None:
    """Move user tracking rows when a company is renamed."""
    from relocation_jobs.db_backend import use_postgres

    ph = "%s" if use_postgres() else "?"
    with db_transaction() as conn:
        for table in ("job_status_events", "job_tracking", "company_tracking"):
            conn.execute(
                f"""
                UPDATE {table}
                SET company_name = {ph}
                WHERE country = {ph} AND company_name = {ph}
                """,
                (new_name, country, old_name),
            )
