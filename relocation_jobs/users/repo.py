from __future__ import annotations

from relocation_jobs.core.db import _normalize_url, get_connection


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
               pinned, pinned_at, updated_at
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
