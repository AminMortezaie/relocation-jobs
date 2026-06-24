from __future__ import annotations

from relocation_jobs.core.db import _normalize_url, _utc_now, db_transaction, get_connection


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
    conn.execute(
        """
        INSERT INTO job_status_events (
            user_id, country, company_name, job_url,
            event_type, event_date, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, country, company_name, job_url, event_type, date_only, _utc_now()),
    )


def status_history_for_job(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> dict[str, list]:
    job_url = _normalize_url(job_url)
    rows = conn.execute(
        """
        SELECT event_type, event_date, created_at
        FROM job_status_events
        WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
        ORDER BY event_date ASC, id ASC
        """,
        (user_id, country, company_name, job_url),
    ).fetchall()
    out: dict[str, list] = {
        "applied": [], "rejected": [], "applied_events": [], "rejected_events": [],
    }
    for row in rows:
        event_type = row.get("event_type", "")
        event_date = (row.get("event_date") or "").strip()
        created_at = (row.get("created_at") or "").strip()
        if event_type not in ("applied", "rejected") or not event_date:
            continue
        out[event_type].append(event_date)
        out[f"{event_type}_events"].append({"date": event_date, "at": created_at})
    return out
