from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from relocation_jobs.core.db import _normalize_url, get_connection


def _timezone(name: str | None) -> ZoneInfo:
    tz = (name or "").strip() or "UTC"
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local_day_utc_bounds(tz: ZoneInfo) -> tuple[str, str]:
    now_local = datetime.now(tz)
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    start_utc = start.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    end_utc = end.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    return start_utc, end_utc


def count_jobs_applied(user_id: int, *, country: str | None = None) -> int:
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


def count_jobs_applied_today(
    user_id: int,
    *,
    country: str | None = None,
    timezone_name: str | None = None,
) -> int:
    return len(list_jobs_applied_today(user_id, country=country, timezone_name=timezone_name))


def list_jobs_applied_today(
    user_id: int,
    *,
    country: str | None = None,
    timezone_name: str | None = None,
) -> list[dict]:
    tz = _timezone(timezone_name)
    start_utc, end_utc = _local_day_utc_bounds(tz)
    conn = get_connection()
    if country:
        rows = conn.execute(
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
    else:
        rows = conn.execute(
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
