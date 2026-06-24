from __future__ import annotations

from relocation_jobs.core.db import _normalize_url, get_connection


def load_job_tracking(user_id: int) -> dict[tuple[str, str, str], dict]:
    rows = get_connection().execute(
        """
        SELECT country, company_name, job_url, job_title, ats_score, applied, applied_date,
               not_for_me, not_for_me_date, not_for_me_reason, rejected, rejected_date,
               waiting_referral, waiting_referral_date, referral_linkedin_url,
               seen, seen_date, looking_to_apply, looking_to_apply_date, updated_at
        FROM job_tracking WHERE user_id = %s
        """,
        (user_id,),
    ).fetchall()
    return {
        (r["country"], r["company_name"], _normalize_url(r["job_url"])): dict(r)
        for r in rows
    }


def load_company_tracking(user_id: int) -> dict[tuple[str, str], dict]:
    rows = get_connection().execute(
        """
        SELECT country, company_name, company_applied, company_applied_date,
               awaiting_response, awaiting_response_date
        FROM company_tracking WHERE user_id = %s
        """,
        (user_id,),
    ).fetchall()
    return {(r["country"], r["company_name"]): dict(r) for r in rows}


def load_job_status_history(user_id: int) -> dict[tuple[str, str, str], dict[str, list]]:
    rows = get_connection().execute(
        """
        SELECT country, company_name, job_url, event_type, event_date, created_at
        FROM job_status_events WHERE user_id = %s
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
