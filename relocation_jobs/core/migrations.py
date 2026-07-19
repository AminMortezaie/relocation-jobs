"""Schema migrations applied at startup."""

from __future__ import annotations

import os
from collections.abc import Callable

from relocation_jobs.core.db import _normalize_url, _utc_now, db_transaction


def _ensure_migrations_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def migration_applied(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = %s",
        (name,),
    ).fetchone()
    return row is not None


def mark_migration_applied(conn, name: str) -> None:
    conn.execute(
        """
        INSERT INTO schema_migrations (name, applied_at)
        VALUES (%s, %s)
        ON CONFLICT (name) DO NOTHING
        """,
        (name, _utc_now()),
    )


def run_migration_once(conn, name: str, fn: Callable) -> None:
    _ensure_migrations_table(conn)
    if migration_applied(conn, name):
        return
    fn(conn)
    mark_migration_applied(conn, name)


def _apply_job_tracking_columns(conn) -> None:
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


def _apply_location_gate_override_column(conn) -> None:
    conn.execute(
        """
        ALTER TABLE job_tracking
        ADD COLUMN IF NOT EXISTS location_gate_override INTEGER NOT NULL DEFAULT 0
        """
    )


def _migrate_schema(conn) -> None:
    """Add columns introduced after initial deploy."""
    run_migration_once(conn, "job_tracking_columns_v1", _apply_job_tracking_columns)
    run_migration_once(conn, "job_status_events_table_v1", _ensure_status_events_table)
    run_migration_once(conn, "job_status_events_backfill_v1", _backfill_job_status_events)
    run_migration_once(conn, "company_tracking_columns_v1", _migrate_company_tracking_schema)
    run_migration_once(conn, "board_pin_columns_v1", _migrate_board_pin_columns)
    run_migration_once(conn, "clear_company_board_pins_v1", _clear_company_board_pins)
    run_migration_once(conn, "fetch_runs_table_v1", _ensure_fetch_runs_table)
    run_migration_once(conn, "fetch_runs_live_state_v1", _migrate_fetch_runs_live_state)
    run_migration_once(conn, "users_admin_column_v1", _ensure_users_admin_column)
    run_migration_once(conn, "mcp_tables_v1", _ensure_mcp_tables)
    run_migration_once(conn, "mcp_master_resumes_v2", _migrate_mcp_master_resumes_v2)
    run_migration_once(conn, "mcp_master_resumes_pdf_v1", _migrate_mcp_master_resumes_pdf_v1)
    run_migration_once(conn, "mcp_applications_country_lower_v1", _migrate_mcp_applications_country_lower)
    run_migration_once(conn, "mcp_cover_letter_v1", _migrate_mcp_cover_letter_v1)
    run_migration_once(conn, "mcp_project_masters_v1", _migrate_mcp_project_masters_v1)
    run_migration_once(conn, "mcp_project_masters_pdf_v1", _migrate_mcp_project_masters_pdf_v1)
    run_migration_once(conn, "mcp_oauth_remote_v1", _ensure_mcp_oauth_remote_tables)
    run_migration_once(conn, "location_gate_override_v1", _apply_location_gate_override_column)


def _migrate_fetch_runs_live_state(conn) -> None:
    conn.execute(
        """
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'done';
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS ats_type TEXT;
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS file_name TEXT;
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS cancel_requested INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS progress_json TEXT;
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS activity_json TEXT;
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS activity_log_json TEXT;
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS log_json TEXT;
        ALTER TABLE fetch_runs ADD COLUMN IF NOT EXISTS review_jobs_json TEXT;
        """
    )
    conn.execute(
        """
        UPDATE fetch_runs
        SET status = 'done'
        WHERE status IS NULL OR TRIM(status) = ''
        """
    )


def _ensure_users_admin_column(conn) -> None:
    conn.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin INTEGER NOT NULL DEFAULT 0"
    )
    admin_name = os.environ.get("PANEL_ADMIN_USER", "admin").strip().lower() or "admin"
    conn.execute(
        "UPDATE users SET is_admin = 1 WHERE LOWER(username) = LOWER(%s)",
        (admin_name,),
    )


def _ensure_mcp_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_user_documents (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            master_resume_tex TEXT NOT NULL DEFAULT '',
            profile_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mcp_applications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            idempotency_key TEXT NOT NULL,
            country TEXT NOT NULL,
            company_name TEXT NOT NULL,
            job_url TEXT NOT NULL,
            tailored_tex TEXT,
            pdf_bytes BYTEA,
            meta_json TEXT NOT NULL DEFAULT '{}',
            tailored_tex_updated_at TEXT,
            pdf_updated_at TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE (user_id, idempotency_key)
        );

        CREATE INDEX IF NOT EXISTS idx_mcp_applications_user
            ON mcp_applications(user_id, updated_at DESC);
        """
    )


def _migrate_mcp_master_resumes_v2(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_master_resumes (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            slug TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, slug)
        );

        ALTER TABLE mcp_applications
        ADD COLUMN IF NOT EXISTS master_resume_slug TEXT;
        """
    )
    conn.execute(
        """
        INSERT INTO mcp_master_resumes (user_id, slug, label, content, updated_at)
        SELECT user_id, 'default', 'Default', master_resume_tex, updated_at
        FROM mcp_user_documents
        WHERE TRIM(COALESCE(master_resume_tex, '')) <> ''
        ON CONFLICT (user_id, slug) DO NOTHING
        """
    )
    conn.execute(
        "ALTER TABLE mcp_user_documents DROP COLUMN IF EXISTS master_resume_tex"
    )


def _migrate_mcp_master_resumes_pdf_v1(conn) -> None:
    conn.execute(
        """
        ALTER TABLE mcp_master_resumes
        ADD COLUMN IF NOT EXISTS pdf_bytes BYTEA;
        ALTER TABLE mcp_master_resumes
        ADD COLUMN IF NOT EXISTS pdf_updated_at TEXT;
        """
    )


def _migrate_mcp_applications_country_lower(conn) -> None:
    conn.execute(
        """
        UPDATE mcp_applications
        SET country = LOWER(TRIM(country))
        WHERE country <> LOWER(TRIM(country))
        """
    )


def _migrate_mcp_cover_letter_v1(conn) -> None:
    conn.execute(
        """
        ALTER TABLE mcp_applications
        ADD COLUMN IF NOT EXISTS cover_letter_tex TEXT;
        ALTER TABLE mcp_applications
        ADD COLUMN IF NOT EXISTS cover_letter_pdf_bytes BYTEA;
        ALTER TABLE mcp_applications
        ADD COLUMN IF NOT EXISTS cover_letter_tex_updated_at TEXT;
        ALTER TABLE mcp_applications
        ADD COLUMN IF NOT EXISTS cover_letter_pdf_updated_at TEXT;
        """
    )


def _migrate_mcp_project_masters_v1(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_project_masters (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            slug TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, slug)
        );
        """
    )


def _migrate_mcp_project_masters_pdf_v1(conn) -> None:
    conn.execute(
        """
        ALTER TABLE mcp_project_masters
        ADD COLUMN IF NOT EXISTS pdf_bytes BYTEA;
        ALTER TABLE mcp_project_masters
        ADD COLUMN IF NOT EXISTS pdf_updated_at TEXT;
        """
    )


def _ensure_mcp_oauth_remote_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_oauth_clients (
            client_id TEXT PRIMARY KEY,
            client_info_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mcp_oauth_pending (
            request_id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            params_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mcp_oauth_auth_codes (
            code_hash TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scopes_json TEXT NOT NULL DEFAULT '[]',
            code_challenge TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            redirect_uri_provided_explicitly INTEGER NOT NULL DEFAULT 0,
            resource TEXT,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mcp_oauth_tokens (
            token_hash TEXT PRIMARY KEY,
            token_kind TEXT NOT NULL,
            client_id TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scopes_json TEXT NOT NULL DEFAULT '[]',
            resource TEXT,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_mcp_oauth_tokens_user
            ON mcp_oauth_tokens(user_id, token_kind);

        CREATE TABLE IF NOT EXISTS mcp_api_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_mcp_api_tokens_user
            ON mcp_api_tokens(user_id);
        """
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


def _migrate_board_pin_columns(conn) -> None:
    conn.execute(
        "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS pinned INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS pinned_at TEXT"
    )
    conn.execute(
        "ALTER TABLE company_tracking ADD COLUMN IF NOT EXISTS board_pinned INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE company_tracking ADD COLUMN IF NOT EXISTS board_pinned_at TEXT"
    )


def _clear_company_board_pins(conn) -> None:
    conn.execute(
        """
        UPDATE company_tracking
        SET board_pinned = 0, board_pinned_at = NULL
        WHERE board_pinned = 1
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
