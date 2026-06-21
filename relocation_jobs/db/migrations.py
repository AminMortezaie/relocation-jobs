"""Schema migrations applied at startup."""

from __future__ import annotations

import os

from relocation_jobs.db.core import _normalize_url, _utc_now, db_transaction


def _migrate_schema(conn) -> None:
    """Add columns introduced after initial deploy."""
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


def _ensure_users_admin_column(conn) -> None:
    conn.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin INTEGER NOT NULL DEFAULT 0"
    )
    admin_name = os.environ.get("PANEL_ADMIN_USER", "admin").strip().lower() or "admin"
    conn.execute(
        "UPDATE users SET is_admin = 1 WHERE LOWER(username) = LOWER(%s)",
        (admin_name,),
    )


def _ensure_fetch_runs_table(conn) -> None:
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


def _migrate_company_tracking_schema(conn) -> None:
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


def _ensure_status_events_table(conn) -> None:
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


def _backfill_job_status_events(conn) -> None:
    """Seed history rows from legacy single applied_date / rejected_date columns."""
    # Lazy import to avoid circular dependency (events → core → migrations → events).
    from relocation_jobs.db.events import _append_job_status_event

    rows = conn.execute(
        """
        SELECT user_id, country, company_name, job_url, applied, applied_date,
               rejected, rejected_date
        FROM job_tracking
        WHERE applied = 1 OR rejected = 1
        """
    ).fetchall()
    now = _utc_now()
    for row in rows:
        user_id = row["user_id"]
        country = row["country"]
        company_name = row["company_name"]
        job_url = _normalize_url(row.get("job_url", ""))
        if not job_url:
            continue
        if row.get("applied") and (row.get("applied_date") or "").strip():
            exists = conn.execute(
                """
                SELECT 1 FROM job_status_events
                WHERE user_id = %s AND country = %s AND company_name = %s
                  AND job_url = %s AND event_type = 'applied'
                LIMIT 1
                """,
                (user_id, country, company_name, job_url),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO job_status_events (
                        user_id, country, company_name, job_url,
                        event_type, event_date, created_at
                    ) VALUES (%s, %s, %s, %s, 'applied', %s, %s)
                    """,
                    (
                        user_id,
                        country,
                        company_name,
                        job_url,
                        (row.get("applied_date") or "").strip(),
                        now,
                    ),
                )
        if row.get("rejected") and (row.get("rejected_date") or "").strip():
            exists = conn.execute(
                """
                SELECT 1 FROM job_status_events
                WHERE user_id = %s AND country = %s AND company_name = %s
                  AND job_url = %s AND event_type = 'rejected'
                LIMIT 1
                """,
                (user_id, country, company_name, job_url),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO job_status_events (
                        user_id, country, company_name, job_url,
                        event_type, event_date, created_at
                    ) VALUES (%s, %s, %s, %s, 'rejected', %s, %s)
                    """,
                    (
                        user_id,
                        country,
                        company_name,
                        job_url,
                        (row.get("rejected_date") or "").strip(),
                        now,
                    ),
                )
