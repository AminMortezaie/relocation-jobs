"""Fetch run recording, live state, listing, and one-time JSON data migration."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from relocation_jobs.core.db import db_transaction, get_connection


def tracking_is_empty() -> bool:
    row = get_connection().execute(
        """
        SELECT (SELECT COUNT(*) FROM job_tracking)
             + (SELECT COUNT(*) FROM company_tracking) AS n
        """
    ).fetchone()
    return int((row or {}).get("n", 0)) == 0


def _duration_seconds(started_at: str, finished_at: str) -> float | None:
    if not (started_at and finished_at):
        return None
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
        return max(0.0, (finish - start).total_seconds())
    except (ValueError, TypeError):
        return None


def _json_dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"))


def _json_loads(raw, default=None):
    if not raw:
        return default if default is not None else None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else None


def _fetch_run_to_dict(row) -> dict:
    if not row:
        return {}
    company_name = (row.get("company_name") or "").strip() or None
    scope = (row.get("scope") or "").strip() or ("company" if company_name else "country")
    finished_at = (row.get("finished_at") or "").strip() or None
    duration = row.get("duration_seconds")
    if duration is None and finished_at:
        duration = _duration_seconds(row.get("started_at", ""), finished_at)
    status = (row.get("status") or "done").strip() or "done"
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "country": row.get("country"),
        "company_name": company_name,
        "scope": scope,
        "status": status,
        "ats_type": (row.get("ats_type") or "").strip() or None,
        "file": (row.get("file_name") or "").strip() or None,
        "started_at": row.get("started_at"),
        "finished_at": finished_at,
        "duration_seconds": duration,
        "exit_code": row.get("exit_code"),
        "cancelled": bool(row.get("cancelled")),
        "cancel_requested": bool(row.get("cancel_requested")),
        "new_jobs": int(row.get("new_jobs") or 0),
        "concurrency": row.get("concurrency"),
        "companies_done": row.get("companies_done"),
        "companies_total": row.get("companies_total"),
        "result_line": row.get("result_line"),
        "progress": _json_loads(row.get("progress_json"), default={}) or {},
        "activity": _json_loads(row.get("activity_json"), default={}) or {},
        "activity_log": _json_loads(row.get("activity_log_json"), default=[]) or [],
        "log": _json_loads(row.get("log_json"), default=[]) or [],
        "review_jobs": _json_loads(row.get("review_jobs_json")),
    }


def fetch_status_from_row(row: dict | None) -> dict:
    data = _fetch_run_to_dict(row) if row else {}
    running = data.get("status") == "running"
    return {
        "running": running,
        "run_id": data.get("id"),
        "country": data.get("country"),
        "company": data.get("company_name"),
        "ats_type": data.get("ats_type"),
        "file": data.get("file"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "exit_code": data.get("exit_code"),
        "concurrency": data.get("concurrency"),
        "result_line": data.get("result_line"),
        "cancel_requested": bool(data.get("cancel_requested")),
        "cancelled": bool(data.get("cancelled")),
        "progress": dict(data.get("progress") or {}),
        "activity": dict(data.get("activity") or {}),
        "activity_log": list(data.get("activity_log") or []),
        "log": list(data.get("log") or []),
        "review_jobs": data.get("review_jobs"),
        "new_jobs_total": int(data.get("new_jobs") or 0),
        "last_fetch_run": None if running else data,
    }


def idle_fetch_status() -> dict:
    return {
        "running": False,
        "run_id": None,
        "country": None,
        "company": None,
        "ats_type": None,
        "file": None,
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "concurrency": None,
        "result_line": None,
        "cancel_requested": False,
        "cancelled": False,
        "progress": {},
        "activity": {},
        "activity_log": [],
        "log": [],
        "review_jobs": None,
        "new_jobs_total": 0,
        "last_fetch_run": None,
    }


def is_fetch_run_cancel_requested(run_id: int) -> bool:
    """True when the panel has requested cancel for a live fetch run (child subprocess poll)."""
    row = get_connection().execute(
        """
        SELECT cancel_requested
        FROM fetch_runs
        WHERE id = %s AND status = 'running'
        """,
        (int(run_id),),
    ).fetchone()
    return bool(row and row.get("cancel_requested"))


def get_running_fetch_run() -> dict | None:
    row = get_connection().execute(
        """
        SELECT *
        FROM fetch_runs
        WHERE status = 'running'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    return _fetch_run_to_dict(row)


def create_fetch_run(
    *,
    user_id: int,
    country: str,
    company_name: str | None,
    file_name: str,
    concurrency: int,
    ats_type: str | None = None,
    started_at: str,
) -> dict:
    company_name = (company_name or "").strip() or None
    scope = "company" if company_name else "country"
    params = (
        int(user_id),
        country,
        company_name,
        scope,
        "running",
        (ats_type or "").strip() or None,
        file_name,
        started_at,
        "",
        int(concurrency),
        0,
        _json_dumps({"current": 0, "total": 0, "company": None, "status": ""}),
        _json_dumps({"message": "", "detail": ""}),
        _json_dumps([]),
        _json_dumps([]),
    )
    with db_transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO fetch_runs (
                user_id, country, company_name, scope, status,
                ats_type, file_name, started_at, finished_at,
                concurrency, new_jobs, progress_json, activity_json,
                activity_log_json, log_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            params,
        ).fetchone()
    return _fetch_run_to_dict(row)


def update_fetch_run_live(
    run_id: int,
    *,
    progress: dict | None = None,
    activity: dict | None = None,
    activity_log: list | None = None,
    log: list | None = None,
    review_jobs: dict | None = None,
    cancel_requested: bool | None = None,
    new_jobs: int | None = None,
    companies_done: int | None = None,
    companies_total: int | None = None,
    result_line: str | None = None,
    concurrency: int | None = None,
) -> None:
    fields: list[str] = []
    params: list = []
    if progress is not None:
        fields.append("progress_json = %s")
        params.append(_json_dumps(progress))
        if companies_done is None:
            companies_done = int(progress.get("current") or 0) or None
        if companies_total is None:
            companies_total = int(progress.get("total") or 0) or None
    if activity is not None:
        fields.append("activity_json = %s")
        params.append(_json_dumps(activity))
    if activity_log is not None:
        fields.append("activity_log_json = %s")
        params.append(_json_dumps(activity_log))
    if log is not None:
        fields.append("log_json = %s")
        params.append(_json_dumps(log))
    if review_jobs is not None:
        fields.append("review_jobs_json = %s")
        params.append(_json_dumps(review_jobs))
    if cancel_requested is not None:
        fields.append("cancel_requested = %s")
        params.append(1 if cancel_requested else 0)
    if new_jobs is not None:
        fields.append("new_jobs = %s")
        params.append(int(new_jobs))
    if companies_done is not None:
        fields.append("companies_done = %s")
        params.append(companies_done)
    if companies_total is not None:
        fields.append("companies_total = %s")
        params.append(companies_total)
    if result_line is not None:
        fields.append("result_line = %s")
        params.append((result_line or "").strip() or None)
    if concurrency is not None:
        fields.append("concurrency = %s")
        params.append(int(concurrency))
    if not fields:
        return
    params.append(int(run_id))
    with db_transaction() as conn:
        conn.execute(
            f"UPDATE fetch_runs SET {', '.join(fields)} WHERE id = %s AND status = 'running'",
            tuple(params),
        )


def finalize_fetch_run(
    run_id: int,
    *,
    finished_at: str,
    exit_code: int | None,
    cancelled: bool = False,
    new_jobs: int = 0,
    concurrency: int | None = None,
    companies_done: int | None = None,
    companies_total: int | None = None,
    result_line: str | None = None,
    progress: dict | None = None,
    activity: dict | None = None,
    activity_log: list | None = None,
    log: list | None = None,
    review_jobs: dict | None = None,
) -> dict | None:
    status = "cancelled" if cancelled else ("done" if exit_code == 0 else "failed")
    duration = None
    started_row = get_connection().execute(
        "SELECT started_at FROM fetch_runs WHERE id = %s",
        (int(run_id),),
    ).fetchone()
    if started_row:
        duration = _duration_seconds(started_row.get("started_at", ""), finished_at)
    params = [
        status,
        finished_at,
        duration,
        exit_code,
        1 if cancelled else 0,
        int(new_jobs or 0),
        concurrency,
        companies_done,
        companies_total,
        (result_line or "").strip() or None,
        _json_dumps(progress) if progress is not None else None,
        _json_dumps(activity) if activity is not None else None,
        _json_dumps(activity_log) if activity_log is not None else None,
        _json_dumps(log) if log is not None else None,
        _json_dumps(review_jobs) if review_jobs is not None else None,
        int(run_id),
    ]
    with db_transaction() as conn:
        row = conn.execute(
            """
            UPDATE fetch_runs
            SET status = %s,
                finished_at = %s,
                duration_seconds = %s,
                exit_code = %s,
                cancelled = %s,
                new_jobs = %s,
                concurrency = %s,
                companies_done = %s,
                companies_total = %s,
                result_line = %s,
                progress_json = COALESCE(%s, progress_json),
                activity_json = COALESCE(%s, activity_json),
                activity_log_json = COALESCE(%s, activity_log_json),
                log_json = COALESCE(%s, log_json),
                review_jobs_json = COALESCE(%s, review_jobs_json),
                cancel_requested = 0
            WHERE id = %s
            RETURNING *
            """,
            tuple(params),
        ).fetchone()
    return _fetch_run_to_dict(row) if row else None


def reap_orphan_running_fetch_runs(*, finished_at: str | None = None) -> int:
    """Mark DB-only running rows failed (e.g. after server restart)."""
    finished_at = finished_at or datetime.now(timezone.utc).isoformat()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            UPDATE fetch_runs
            SET status = 'failed',
                finished_at = %s,
                exit_code = 1,
                result_line = COALESCE(result_line, 'Fetch interrupted (server restarted)')
            WHERE status = 'running'
            """,
            (finished_at,),
        )
    return int(cur.rowcount or 0)


def clear_running_fetch_runs_for_tests() -> None:
    with db_transaction() as conn:
        conn.execute("DELETE FROM fetch_runs WHERE status = 'running'")


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
    status = "cancelled" if cancelled else ("done" if exit_code == 0 else "failed")
    duration = _duration_seconds(started_at, finished_at)
    params = (
        int(user_id),
        country,
        company_name,
        scope,
        status,
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
        row = conn.execute(
            """
            INSERT INTO fetch_runs (
                user_id, country, company_name, scope, status,
                started_at, finished_at, duration_seconds,
                exit_code, cancelled, new_jobs, concurrency,
                companies_done, companies_total, result_line
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            params,
        ).fetchone()
    return _fetch_run_to_dict(row)


def list_fetch_runs(
    user_id: int,
    *,
    country: str | None = None,
    limit: int = 20,
) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    sql = """
        SELECT * FROM fetch_runs
        WHERE user_id = %s AND status != 'running'
    """
    params: list = [int(user_id)]
    if country:
        sql += " AND country = %s"
        params.append(country)
    sql += f" ORDER BY started_at DESC, id DESC LIMIT {limit}"
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    return [_fetch_run_to_dict(row) for row in rows]


def list_all_fetch_runs(
    *,
    country: str | None = None,
    limit: int = 50,
) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    sql = """
        SELECT f.*, u.username
        FROM fetch_runs f
        JOIN users u ON u.id = f.user_id
        WHERE f.status != 'running'
    """
    params: list = []
    if country:
        sql += " AND f.country = %s"
        params.append(country)
    sql += f" ORDER BY f.started_at DESC, f.id DESC LIMIT {limit}"
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    out: list[dict] = []
    for row in rows:
        data = _fetch_run_to_dict(row)
        data["username"] = row.get("username")
        out.append(data)
    return out
