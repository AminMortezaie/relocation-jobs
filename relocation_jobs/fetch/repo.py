from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from relocation_jobs.core.db import db_transaction, get_connection
from relocation_jobs.fetch.types import AttemptStatus, CompanyFetchAttempt
from relocation_jobs.users.applied import local_day_utc_bounds


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _duration_seconds(started_at: str, finished_at: str) -> float | None:
    if not (started_at and finished_at):
        return None
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
        return max(0.0, (finish - start).total_seconds())
    except (ValueError, TypeError):
        return None


def panel_fetch_run_id() -> int | None:
    raw = (os.environ.get("PANEL_FETCH_RUN_ID") or "").strip()
    return int(raw) if raw.isdigit() else None


def insert_attempt(
    *,
    country: str,
    company_name: str,
    careers_url: str = "",
    ats_type: str = "",
    fetch_run_id: int | None = None,
) -> int:
    started_at = _utc_now()
    run_id = fetch_run_id if fetch_run_id is not None else panel_fetch_run_id()
    with db_transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO company_fetch_attempts (
                fetch_run_id, country, company_name, careers_url, ats_type,
                started_at, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                run_id,
                country,
                company_name,
                (careers_url or "").strip() or None,
                (ats_type or "").strip() or None,
                started_at,
                AttemptStatus.RUNNING.value,
            ),
        ).fetchone()
    return int(row["id"])


def update_attempt(
    attempt_id: int,
    *,
    status: AttemptStatus,
    error_message: str | None = None,
    jobs_total: int | None = None,
    jobs_new: int | None = None,
    jobs_preserved: int | None = None,
    message: str | None = None,
) -> None:
    finished_at = _utc_now()
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT started_at FROM company_fetch_attempts WHERE id = %s",
            (attempt_id,),
        ).fetchone()
        started_at = (row or {}).get("started_at") or ""
        duration = _duration_seconds(started_at, finished_at)
        conn.execute(
            """
            UPDATE company_fetch_attempts
            SET finished_at = %s,
                status = %s,
                error_message = %s,
                jobs_total = %s,
                jobs_new = %s,
                jobs_preserved = %s,
                message = %s,
                duration_seconds = %s
            WHERE id = %s
            """,
            (
                finished_at,
                status.value,
                (error_message or "").strip() or None,
                jobs_total,
                jobs_new,
                jobs_preserved,
                (message or "").strip() or None,
                duration,
                attempt_id,
            ),
        )


def list_attempts(
    *,
    country: str | None = None,
    company_name: str | None = None,
    fetch_run_id: int | None = None,
    status: AttemptStatus | None = None,
    limit: int = 100,
) -> list[CompanyFetchAttempt]:
    clauses: list[str] = []
    params: list = []
    if country:
        clauses.append("country = %s")
        params.append(country)
    if company_name:
        clauses.append("company_name = %s")
        params.append(company_name)
    if fetch_run_id is not None:
        clauses.append("fetch_run_id = %s")
        params.append(fetch_run_id)
    if status is not None:
        clauses.append("status = %s")
        params.append(status.value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(int(limit), 500)))
    rows = get_connection().execute(
        f"""
        SELECT id, fetch_run_id, country, company_name, careers_url, ats_type,
               started_at, finished_at, status, error_message,
               jobs_total, jobs_new, jobs_preserved, message, duration_seconds
        FROM company_fetch_attempts
        {where}
        ORDER BY started_at DESC
        LIMIT %s
        """,
        tuple(params),
    ).fetchall()
    return [CompanyFetchAttempt.from_row(dict(row)) for row in rows]


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


def _fetch_run_row_to_dict(row) -> dict:
    if not row:
        return {}
    data = dict(row)
    company_name = (data.get("company_name") or "").strip() or None
    scope = (data.get("scope") or "").strip() or ("company" if company_name else "country")
    finished_at = (data.get("finished_at") or "").strip() or None
    duration = data.get("duration_seconds")
    if duration is None and finished_at:
        duration = _duration_seconds(data.get("started_at", ""), finished_at)
    status = (data.get("status") or "done").strip() or "done"
    return {
        "id": data.get("id"),
        "user_id": data.get("user_id"),
        "country": data.get("country"),
        "company_name": company_name,
        "scope": scope,
        "status": status,
        "ats_type": (data.get("ats_type") or "").strip() or None,
        "file": (data.get("file_name") or "").strip() or None,
        "started_at": data.get("started_at"),
        "finished_at": finished_at,
        "duration_seconds": duration,
        "exit_code": data.get("exit_code"),
        "cancelled": bool(data.get("cancelled")),
        "cancel_requested": bool(data.get("cancel_requested")),
        "new_jobs": int(data.get("new_jobs") or 0),
        "concurrency": data.get("concurrency"),
        "companies_done": data.get("companies_done"),
        "companies_total": data.get("companies_total"),
        "result_line": data.get("result_line"),
        "progress": _json_loads(data.get("progress_json"), default={}) or {},
        "activity": _json_loads(data.get("activity_json"), default={}) or {},
        "activity_log": _json_loads(data.get("activity_log_json"), default=[]) or [],
        "log": _json_loads(data.get("log_json"), default=[]) or [],
        "review_jobs": _json_loads(data.get("review_jobs_json")),
    }


def list_user_fetch_runs(
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
    return [_fetch_run_row_to_dict(row) for row in rows]


def sum_new_jobs_today(
    user_id: int,
    *,
    country: str | None = None,
    timezone_name: str | None = None,
) -> int:
    start_utc, end_utc = local_day_utc_bounds(timezone_name)
    sql = """
        SELECT COALESCE(SUM(new_jobs), 0) AS total
        FROM fetch_runs
        WHERE user_id = %s
          AND status != 'running'
          AND finished_at >= %s
          AND finished_at < %s
    """
    params: list = [int(user_id), start_utc, end_utc]
    if country:
        sql += " AND country = %s"
        params.append(country)
    row = get_connection().execute(sql, tuple(params)).fetchone()
    return int((row or {}).get("total") or 0)


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
        data = _fetch_run_row_to_dict(row)
        data["username"] = row.get("username")
        out.append(data)
    return out


def latest_finished_country_run() -> dict | None:
    row = get_connection().execute(
        """
        SELECT f.*, u.username
        FROM fetch_runs f
        JOIN users u ON u.id = f.user_id
        WHERE f.status != 'running'
          AND f.scope = 'country'
          AND (f.company_name IS NULL OR TRIM(f.company_name) = '')
        ORDER BY f.finished_at DESC, f.id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    data = _fetch_run_row_to_dict(row)
    data["username"] = row.get("username")
    return data


def fetch_run_is_running(run_id: int) -> bool:
    row = get_connection().execute(
        "SELECT status FROM fetch_runs WHERE id = %s",
        (int(run_id),),
    ).fetchone()
    return bool(row and row.get("status") == "running")


def get_running_fetch_run() -> dict | None:
    row = get_connection().execute(
        """
        SELECT * FROM fetch_runs
        WHERE status = 'running'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    return _fetch_run_row_to_dict(row)


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
    return _fetch_run_row_to_dict(row)


def update_fetch_run_live(
    run_id: int,
    *,
    progress: dict | None = None,
    activity: dict | None = None,
    activity_log: list | None = None,
    log: list | None = None,
    cancel_requested: bool | None = None,
    new_jobs: int | None = None,
    companies_done: int | None = None,
    companies_total: int | None = None,
    result_line: str | None = None,
    review_jobs: dict | None = None,
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
    if review_jobs is not None:
        fields.append("review_jobs_json = %s")
        params.append(_json_dumps(review_jobs))
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
    started_row = get_connection().execute(
        "SELECT started_at FROM fetch_runs WHERE id = %s",
        (int(run_id),),
    ).fetchone()
    duration = None
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
            WHERE id = %s AND status = 'running'
            RETURNING *
            """,
            tuple(params),
        ).fetchone()
    return _fetch_run_row_to_dict(row) if row else None


def fetch_run_cancel_requested(run_id: int) -> bool:
    row = get_connection().execute(
        """
        SELECT cancel_requested
        FROM fetch_runs
        WHERE id = %s AND status = 'running'
        """,
        (int(run_id),),
    ).fetchone()
    return bool(row and row.get("cancel_requested"))


def request_fetch_run_cancel(run_id: int) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE fetch_runs
            SET cancel_requested = 1
            WHERE id = %s AND status = 'running'
            """,
            (int(run_id),),
        )


def reap_orphan_running_fetch_runs(*, finished_at: str | None = None) -> int:
    finished_at = finished_at or _utc_now()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            UPDATE fetch_runs
            SET status = 'failed',
                finished_at = %s,
                exit_code = 1,
                result_line = COALESCE(result_line, 'Fetch interrupted (orphan reap)')
            WHERE status = 'running'
            """,
            (finished_at,),
        )
    return int(cur.rowcount or 0)


def clear_running_fetch_runs_for_tests() -> None:
    with db_transaction() as conn:
        conn.execute("DELETE FROM fetch_runs WHERE status = 'running'")


def delete_fetch_runs_for_country(country_key: str) -> int:
    key = (country_key or "").strip().lower()
    with db_transaction() as conn:
        rows = conn.execute(
            "DELETE FROM fetch_runs WHERE country = %s RETURNING id",
            (key,),
        ).fetchall()
    return len(rows)
