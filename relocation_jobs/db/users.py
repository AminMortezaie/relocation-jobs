"""User CRUD and admin user helpers."""

from __future__ import annotations

import os

from relocation_jobs.core.db import _utc_now, db_transaction, get_connection
from relocation_jobs.core.migrations import _ensure_users_admin_column


def user_count() -> int:
    row = get_connection().execute("SELECT COUNT(*) AS n FROM users").fetchone()
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
    row = get_connection().execute(
        """
        SELECT id, username, password_hash, created_at
        FROM users WHERE LOWER(username) = LOWER(%s)
        """,
        (username.strip(),),
    ).fetchone()
    return row or None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
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
