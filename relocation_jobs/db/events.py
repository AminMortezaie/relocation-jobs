"""Job status events: apply/reject history and applied-today queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from relocation_jobs.db.core import _normalize_url, _utc_now, db_transaction, get_connection


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
    conn.execute(
        """
        INSERT INTO job_status_events (
            user_id, country, company_name, job_url,
            event_type, event_date, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        "applied": [],
        "rejected": [],
        "applied_events": [],
        "rejected_events": [],
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


def load_job_status_history(user_id: int) -> dict[tuple[str, str, str], dict[str, list]]:
    """All apply/reject events keyed by (country, company, normalized job_url)."""
    rows = get_connection().execute(
        """
        SELECT country, company_name, job_url, event_type, event_date, created_at
        FROM job_status_events
        WHERE user_id = %s
        ORDER BY event_date ASC, id ASC
        """,
        (user_id,),
    ).fetchall()
    out: dict[tuple[str, str, str], dict[str, list]] = {}
    for row in rows:
        key = (row["country"], row["company_name"], _normalize_url(row.get("job_url", "")))
        if not key[2]:
            continue
        bucket = out.setdefault(
            key,
            {"applied": [], "rejected": [], "applied_events": [], "rejected_events": []},
        )
        event_type = row.get("event_type", "")
        event_date = (row.get("event_date") or "").strip()
        created_at = (row.get("created_at") or "").strip()
        if event_type not in ("applied", "rejected") or not event_date:
            continue
        bucket[event_type].append(event_date)
        bucket[f"{event_type}_events"].append({"date": event_date, "at": created_at})
    return out


def count_jobs_applied_db(user_id: int, *, country: str | None = None) -> int:
    """Count positions currently marked applied for the user."""
    conn = get_connection()
    if country:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM job_tracking
            WHERE user_id = %s AND applied = 1 AND country = %s
            """,
            (user_id, country),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM job_tracking
            WHERE user_id = %s AND applied = 1
            """,
            (user_id,),
        ).fetchone()
    return int((row or {}).get("n") or 0)


def _applied_today_event_rows(
    conn,
    user_id: int,
    start_utc: str,
    end_utc: str,
    country: str | None,
) -> list:
    if country:
        return conn.execute(
            """
            SELECT e.country, e.company_name, e.job_url, e.event_date, e.created_at,
                   t.job_title
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
        SELECT e.country, e.company_name, e.job_url, e.event_date, e.created_at,
               t.job_title
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


def _jobs_applied_today_from_rows(rows: list) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for row in rows:
        url = _normalize_url(row.get("job_url", ""))
        if not url:
            continue
        key = (row["country"], row["company_name"], url)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "country": row["country"],
            "company": row["company_name"],
            "url": url,
            "title": (row.get("job_title") or "").strip(),
            "event_date": (row.get("event_date") or "").strip(),
            "applied_at": (row.get("created_at") or "").strip(),
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
