from __future__ import annotations

import os

from relocation_jobs.core.db import _normalize_url, _utc_now, db_read, db_transaction, get_connection
from relocation_jobs.core.migrations import _ensure_users_admin_column


def _empty_status_history() -> dict[str, list]:
    return {
        "applied": [],
        "rejected": [],
        "applied_events": [],
        "rejected_events": [],
    }


def _append_status_event_row(bucket: dict[str, list], row: dict) -> None:
    event_type = row.get("event_type", "")
    event_date = (row.get("event_date") or "").strip()
    created_at = (row.get("created_at") or "").strip()
    if event_type not in ("applied", "rejected") or not event_date:
        return
    bucket[event_type].append(event_date)
    bucket[f"{event_type}_events"].append({"date": event_date, "at": created_at})


def shape_status_history(rows: list[dict]) -> dict[str, list]:
    bucket = _empty_status_history()
    for row in rows:
        _append_status_event_row(bucket, row)
    return bucket


def load_job_tracking(user_id: int, *, country: str | None = None) -> dict[tuple[str, str, str], dict]:
    sql = """
        SELECT country, company_name, job_url, job_title, ats_score, applied, applied_date,
               not_for_me, not_for_me_date, not_for_me_reason, rejected, rejected_date,
               waiting_referral, waiting_referral_date, referral_linkedin_url,
               seen, seen_date, looking_to_apply, looking_to_apply_date,
               pinned, pinned_at, location_gate_override, updated_at
        FROM job_tracking WHERE user_id = %s
    """
    params: list = [user_id]
    if country and country != "all":
        sql += " AND country = %s"
        params.append(country)
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    return {
        (r["country"], r["company_name"], _normalize_url(r["job_url"])): dict(r)
        for r in rows
    }


def load_company_tracking(user_id: int, *, country: str | None = None) -> dict[tuple[str, str], dict]:
    sql = """
        SELECT country, company_name, company_applied, company_applied_date,
               awaiting_response, awaiting_response_date,
               board_pinned, board_pinned_at
        FROM company_tracking WHERE user_id = %s
    """
    params: list = [user_id]
    if country and country != "all":
        sql += " AND country = %s"
        params.append(country)
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    return {(r["country"], r["company_name"]): dict(r) for r in rows}


def load_job_status_history(user_id: int, *, country: str | None = None) -> dict[tuple[str, str, str], dict[str, list]]:
    sql = """
        SELECT country, company_name, job_url, event_type, event_date, created_at
        FROM job_status_events WHERE user_id = %s
    """
    params: list = [user_id]
    if country and country != "all":
        sql += " AND country = %s"
        params.append(country)
    sql += " ORDER BY event_date ASC, id ASC"
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    out: dict[tuple[str, str, str], dict[str, list]] = {}
    for row in rows:
        key = (row["country"], row["company_name"], _normalize_url(row.get("job_url", "")))
        if not key[2]:
            continue
        bucket = out.setdefault(key, _empty_status_history())
        _append_status_event_row(bucket, row)
    return out


def insert_status_event(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    event_type: str,
    event_date: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO job_status_events (
            user_id, country, company_name, job_url,
            event_type, event_date, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, country, company_name, job_url, event_type, event_date, created_at),
    )


def fetch_status_events_for_job(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> list[dict]:
    return conn.execute(
        """
        SELECT event_type, event_date, created_at
        FROM job_status_events
        WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
        ORDER BY event_date ASC, id ASC
        """,
        (user_id, country, company_name, job_url),
    ).fetchall()


def count_applied_jobs(user_id: int, *, country: str | None = None) -> int:
    conn = get_connection()
    if country:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM job_tracking WHERE user_id = %s AND applied = 1 AND country = %s",
            (user_id, country),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM job_tracking WHERE user_id = %s AND applied = 1",
            (user_id,),
        ).fetchone()
    return int((row or {}).get("n") or 0)


def fetch_applied_events_in_range(
    user_id: int,
    start_utc: str,
    end_utc: str,
    *,
    country: str | None = None,
) -> list[dict]:
    conn = get_connection()
    if country:
        return conn.execute(
            """
            SELECT e.country, e.company_name, e.job_url, e.event_date, e.created_at, t.job_title
            FROM job_status_events e
            LEFT JOIN job_tracking t
              ON t.user_id = e.user_id AND t.country = e.country
             AND t.company_name = e.company_name AND t.job_url = e.job_url
            WHERE e.user_id = %s AND e.event_type = 'applied' AND e.country = %s
              AND e.created_at >= %s AND e.created_at < %s
            ORDER BY e.created_at DESC
            """,
            (user_id, country, start_utc, end_utc),
        ).fetchall()
    return conn.execute(
        """
        SELECT e.country, e.company_name, e.job_url, e.event_date, e.created_at, t.job_title
        FROM job_status_events e
        LEFT JOIN job_tracking t
          ON t.user_id = e.user_id AND t.country = e.country
         AND t.company_name = e.company_name AND t.job_url = e.job_url
        WHERE e.user_id = %s AND e.event_type = 'applied'
          AND e.created_at >= %s AND e.created_at < %s
        ORDER BY e.created_at DESC
        """,
        (user_id, start_utc, end_utc),
    ).fetchall()


def user_count() -> int:
    with db_read() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int((row or {}).get("n", 0))


def create_user(username: str, password_hash: str, *, is_admin: bool = False) -> dict:
    username = username.strip()
    if not username:
        raise ValueError("Username is required")
    now = _utc_now()
    admin_flag = 1 if is_admin else 0
    with db_transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (username, password_hash, now, admin_flag),
        ).fetchone()
        user_id = int(row["id"])
    return {
        "id": user_id,
        "username": username,
        "created_at": now,
        "is_admin": bool(is_admin),
    }


def get_user_by_username(username: str) -> dict | None:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, created_at
            FROM users WHERE LOWER(username) = LOWER(%s)
            """,
            (username.strip(),),
        ).fetchone()
    return row or None


def resolve_scheduler_user_id() -> int:
    admin_name = os.environ.get("PANEL_ADMIN_USER", "admin").strip() or "admin"
    user = get_user_by_username(admin_name)
    if not user:
        raise LookupError(f"Scheduler admin user not found: {admin_name}")
    return int(user["id"])


def get_user_by_id(user_id: int) -> dict | None:
    with db_read() as conn:
        try:
            row = conn.execute(
                "SELECT id, username, created_at, is_admin FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()
        except Exception as exc:
            if "is_admin" not in str(exc).lower():
                raise
            with db_transaction() as migrate_conn:
                _ensure_users_admin_column(migrate_conn)
            row = conn.execute(
                "SELECT id, username, created_at, is_admin FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()
    if not row:
        return None
    data = dict(row)
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
    with db_read() as conn:
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
        username = (row.get("username") or "").strip()
        out.append(
            {
                "id": row["id"],
                "username": username,
                "created_at": row.get("created_at"),
                "is_admin": bool(row.get("is_admin")) or username.lower() == admin_name,
                "tracking_rows": int(row.get("tracking_rows") or 0),
                "applied_positions": int(row.get("applied_positions") or 0),
                "rejected_positions": int(row.get("rejected_positions") or 0),
                "not_for_me_positions": int(row.get("not_for_me_positions") or 0),
                "fetch_runs": int(row.get("fetch_runs") or 0),
            }
        )
    return out


def admin_tracking_totals() -> dict:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS tracking_rows,
                COUNT(*) FILTER (WHERE applied = 1) AS applied_positions,
                COUNT(*) FILTER (WHERE rejected = 1) AS rejected_positions,
                COUNT(*) FILTER (WHERE not_for_me = 1) AS not_for_me_positions
            FROM job_tracking
            """
        ).fetchone()
    return {
        "tracking_rows": int((row or {}).get("tracking_rows") or 0),
        "applied_positions": int((row or {}).get("applied_positions") or 0),
        "rejected_positions": int((row or {}).get("rejected_positions") or 0),
        "not_for_me_positions": int((row or {}).get("not_for_me_positions") or 0),
    }


def update_user_password(username: str, password_hash: str) -> bool:
    with db_transaction() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = %s WHERE LOWER(username) = LOWER(%s)",
            (password_hash, username.strip()),
        )
        return cur.rowcount > 0


def rename_user(user_id: int, username: str) -> bool:
    username = username.strip()
    with db_transaction() as conn:
        cur = conn.execute(
            "UPDATE users SET username = %s WHERE id = %s",
            (username, user_id),
        )
        return cur.rowcount > 0
