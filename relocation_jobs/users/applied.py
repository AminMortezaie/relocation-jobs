from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from relocation_jobs.core.db import _normalize_url
from relocation_jobs.users.repo import count_applied_jobs, fetch_applied_events_in_range


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
    return count_applied_jobs(user_id, country=country)


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
    rows = fetch_applied_events_in_range(
        user_id, start_utc, end_utc, country=country,
    )
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
