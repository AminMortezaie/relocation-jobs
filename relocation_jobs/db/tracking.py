"""Per-user job tracking: applied, rejected, seen, referral, ATS score."""

from __future__ import annotations

from relocation_jobs.job_identity import job_idempotency_key
from relocation_jobs.db.core import _normalize_url, _utc_now, db_transaction, get_connection
from relocation_jobs.db.events import (
    _append_job_status_event,
    _load_status_history_for_job,
)


def _resolve_tracking_url(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> str:
    """Return the tracking row URL for this job (exact or idempotency alias)."""
    job_url = _normalize_url(job_url)
    job_key = job_idempotency_key(job_url)
    if not job_key:
        return job_url
    rows = conn.execute(
        """
        SELECT job_url FROM job_tracking
        WHERE user_id = %s AND country = %s AND company_name = %s
        """,
        (user_id, country, company_name),
    ).fetchall()
    alias = job_url
    for row in rows:
        stored = _normalize_url(row.get("job_url", ""))
        if stored == job_url:
            return job_url
        if job_idempotency_key(stored) == job_key:
            alias = stored
    return alias


def _tracking_urls_for_job(
    conn,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> set[str]:
    """All tracking URLs that refer to the same job (normalized + idempotency aliases)."""
    canonical_url = _normalize_url(job_url)
    urls = {canonical_url}
    job_key = job_idempotency_key(canonical_url)
    if not job_key:
        return urls
    rows = conn.execute(
        """
        SELECT job_url FROM job_tracking
        WHERE user_id = %s AND country = %s AND company_name = %s
        """,
        (user_id, country, company_name),
    ).fetchall()
    for row in rows:
        stored = _normalize_url(row.get("job_url", ""))
        if job_idempotency_key(stored) == job_key:
            urls.add(stored)
    return urls


def load_job_tracking(user_id: int) -> dict[tuple[str, str, str], dict]:
    rows = get_connection().execute(
        """
        SELECT country, company_name, job_url, job_title, ats_score, applied, applied_date,
               not_for_me, not_for_me_date, not_for_me_reason, rejected, rejected_date,
               waiting_referral, waiting_referral_date, referral_linkedin_url,
               seen, seen_date, looking_to_apply, looking_to_apply_date, updated_at
        FROM job_tracking
        WHERE user_id = %s
        """,
        (user_id,),
    ).fetchall()
    out: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row["country"], row["company_name"], _normalize_url(row["job_url"]))
        out[key] = row
    return out


def set_job_applied_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    applied: bool,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    preserved_looking_to_apply_date = ""
    with db_transaction() as conn:
        if applied:
            title = (job_title or "").strip()
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    applied, applied_date, not_for_me, not_for_me_date,
                    looking_to_apply, looking_to_apply_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 1, %s, 0, NULL, 0, NULL, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    applied = 1,
                    applied_date = EXCLUDED.applied_date,
                    looking_to_apply = 0,
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, job_url, title, now[:10], now),
            )
            applied_date = now[:10]
            _append_job_status_event(
                conn, user_id, country, company_name, job_url, "applied",
                event_date=applied_date,
            )
            row = conn.execute(
                """
                SELECT looking_to_apply_date
                FROM job_tracking
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (user_id, country, company_name, job_url),
            ).fetchone()
            preserved_looking_to_apply_date = (row["looking_to_apply_date"] or "") if row else ""
        else:
            conn.execute(
                """
                UPDATE job_tracking
                SET applied = 0, applied_date = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, job_url),
            )
            applied_date = ""
    result = {
        "applied": applied,
        "applied_date": applied_date if applied else "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }
    if applied:
        result["looking_to_apply"] = False
        result["looking_to_apply_date"] = preserved_looking_to_apply_date
    with db_transaction() as conn:
        history = _load_status_history_for_job(conn, user_id, country, company_name, job_url)
    latest_applied = max(history["applied"]) if history["applied"] else ""
    if latest_applied:
        result["applied_date"] = latest_applied
    latest_applied_at = max(
        ((event.get("at") or "").strip() for event in history.get("applied_events") or []),
        default="",
    )
    if latest_applied_at:
        result["applied_at"] = latest_applied_at
    elif applied:
        result["applied_at"] = now
    result["applied_history"] = history["applied"]
    result["applied_events"] = history.get("applied_events") or []
    result["rejected_history"] = history["rejected"]
    return result


def set_job_not_for_me_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    *,
    not_for_me: bool = True,
    reason: str | None = None,
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    date_only = now[:10]
    hide_reason = (reason or "not_for_me").strip() or "not_for_me"
    with db_transaction() as conn:
        if not_for_me:
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url,
                    applied, applied_date, not_for_me, not_for_me_date,
                    not_for_me_reason, updated_at
                ) VALUES (%s, %s, %s, %s, 0, NULL, 1, %s, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    not_for_me = 1,
                    not_for_me_date = EXCLUDED.not_for_me_date,
                    not_for_me_reason = EXCLUDED.not_for_me_reason,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, job_url, date_only, hide_reason, now),
            )
            return {
                "not_for_me": True,
                "not_for_me_date": date_only,
                "not_for_me_reason": hide_reason,
                "company": company_name,
                "url": job_url,
                "country": country,
            }
        conn.execute(
            """
            UPDATE job_tracking
            SET not_for_me = 0, not_for_me_date = NULL, not_for_me_reason = NULL,
                updated_at = %s
            WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
            """,
            (now, user_id, country, company_name, job_url),
        )
    return {
        "not_for_me": False,
        "not_for_me_date": "",
        "not_for_me_reason": "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_rejected_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    rejected: bool,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        if rejected:
            title = (job_title or "").strip()
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    applied, applied_date, not_for_me, not_for_me_date,
                    rejected, rejected_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    rejected = 1,
                    rejected_date = EXCLUDED.rejected_date,
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, job_url, title, now[:10], now),
            )
            rejected_date = now[:10]
            _append_job_status_event(
                conn, user_id, country, company_name, job_url, "rejected",
                event_date=rejected_date,
            )
        else:
            conn.execute(
                """
                UPDATE job_tracking
                SET rejected = 0, rejected_date = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, job_url),
            )
            rejected_date = ""
    with db_transaction() as conn:
        history = _load_status_history_for_job(conn, user_id, country, company_name, job_url)
    latest_rejected = max(history["rejected"]) if history["rejected"] else ""
    result_rejected_date = latest_rejected if latest_rejected else (rejected_date if rejected else "")
    latest_applied = max(history["applied"]) if history["applied"] else ""
    return {
        "rejected": rejected,
        "rejected_date": result_rejected_date,
        "applied_date": latest_applied,
        "applied_history": history["applied"],
        "rejected_history": history["rejected"],
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def reapply_job_db(user_id: int, country: str, company_name: str, job_url: str) -> dict:
    """Clear active rejection so the role returns to the main positions list."""
    return set_job_rejected_db(user_id, country, company_name, job_url, rejected=False)


def set_job_looking_to_apply_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    looking_to_apply: bool,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        if looking_to_apply:
            title = (job_title or "").strip()
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    applied, applied_date, not_for_me, not_for_me_date,
                    looking_to_apply, looking_to_apply_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    looking_to_apply = 1,
                    looking_to_apply_date = EXCLUDED.looking_to_apply_date,
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, job_url, title, now[:10], now),
            )
            looking_to_apply_date = now[:10]
        else:
            conn.execute(
                """
                UPDATE job_tracking
                SET looking_to_apply = 0, looking_to_apply_date = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, job_url),
            )
            looking_to_apply_date = ""
    return {
        "looking_to_apply": looking_to_apply,
        "looking_to_apply_date": looking_to_apply_date if looking_to_apply else "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_seen_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    seen: bool = True,
    *,
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        storage_url = _resolve_tracking_url(conn, user_id, country, company_name, canonical_url)
        if seen:
            title = (job_title or "").strip()
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    applied, applied_date, not_for_me, not_for_me_date,
                    seen, seen_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    seen = 1,
                    seen_date = COALESCE(job_tracking.seen_date, EXCLUDED.seen_date),
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, storage_url, title, now[:10], now),
            )
            if storage_url != canonical_url:
                conn.execute(
                    """
                    INSERT INTO job_tracking (
                        user_id, country, company_name, job_url, job_title,
                        applied, applied_date, not_for_me, not_for_me_date,
                        seen, seen_date, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s)
                    ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                        seen = 1,
                        seen_date = COALESCE(job_tracking.seen_date, EXCLUDED.seen_date),
                        job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, country, company_name, canonical_url, title, now[:10], now),
                )
            row = conn.execute(
                "SELECT seen_date FROM job_tracking WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s",
                (user_id, country, company_name, canonical_url),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT seen_date FROM job_tracking WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s",
                    (user_id, country, company_name, storage_url),
                ).fetchone()
            seen_date = (row["seen_date"] if row else None) or now[:10]
        else:
            urls_to_clear = _tracking_urls_for_job(conn, user_id, country, company_name, canonical_url)
            for url in urls_to_clear:
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET seen = 0, seen_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, url),
                )
            seen_date = ""
    return {
        "seen": seen,
        "seen_date": seen_date if seen else "",
        "idempotency_key": job_idempotency_key(canonical_url),
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_waiting_referral_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    waiting_referral: bool,
    *,
    linkedin_url: str = "",
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    date_only = now[:10]
    linkedin = (linkedin_url or "").strip()
    with db_transaction() as conn:
        if waiting_referral:
            if not linkedin:
                raise ValueError("LinkedIn profile URL is required")
            title = (job_title or "").strip()
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    applied, applied_date, not_for_me, not_for_me_date,
                    waiting_referral, waiting_referral_date, referral_linkedin_url,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, 0, NULL, 0, NULL, 1, %s, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    waiting_referral = 1,
                    waiting_referral_date = EXCLUDED.waiting_referral_date,
                    referral_linkedin_url = EXCLUDED.referral_linkedin_url,
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, job_url, title, date_only, linkedin, now),
            )
            return {
                "waiting_referral": True,
                "waiting_referral_date": date_only,
                "referral_linkedin_url": linkedin,
                "company": company_name,
                "url": job_url,
                "country": country,
            }
        conn.execute(
            """
            UPDATE job_tracking
            SET waiting_referral = 0, waiting_referral_date = NULL,
                referral_linkedin_url = NULL, updated_at = %s
            WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
            """,
            (now, user_id, country, company_name, job_url),
        )
    return {
        "waiting_referral": False,
        "waiting_referral_date": "",
        "referral_linkedin_url": "",
        "company": company_name,
        "url": job_url,
        "country": country,
    }


def set_job_ats_score_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    ats_score: int | None,
    *,
    job_title: str = "",
) -> dict:
    job_url = _normalize_url(job_url)
    now = _utc_now()
    title = (job_title or "").strip()
    with db_transaction() as conn:
        if ats_score is not None:
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title, ats_score,
                    applied, applied_date, not_for_me, not_for_me_date,
                    rejected, rejected_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 0, NULL, 0, NULL, 0, NULL, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    ats_score = EXCLUDED.ats_score,
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, job_url, title, ats_score, now),
            )
        else:
            conn.execute(
                """
                UPDATE job_tracking
                SET ats_score = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, job_url),
            )
    return {
        "ats_score": ats_score,
        "company": company_name,
        "url": job_url,
        "country": country,
    }
