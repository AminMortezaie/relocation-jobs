from __future__ import annotations

from relocation_jobs.core.db import _normalize_url, _utc_now
from relocation_jobs.v2.users.repo import (
    fetch_status_events_for_job,
    insert_status_event,
    shape_status_history,
)


def append_status_event(
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
    insert_status_event(
        conn,
        user_id,
        country,
        company_name,
        job_url,
        event_type,
        date_only,
        _utc_now(),
    )


def status_history_for_job(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> dict[str, list]:
    job_url = _normalize_url(job_url)
    rows = fetch_status_events_for_job(conn, user_id, country, company_name, job_url)
    return shape_status_history(rows)
