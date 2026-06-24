from __future__ import annotations

import os
from datetime import datetime, timezone

from relocation_jobs.core.db import db_transaction, get_connection
from relocation_jobs.v2.fetch.types import AttemptStatus, CompanyFetchAttempt


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
