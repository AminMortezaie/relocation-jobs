from __future__ import annotations

from relocation_jobs.core.job_identity import job_idempotency_key
from relocation_jobs.core.db import _normalize_url, _utc_now, db_transaction, get_connection
from relocation_jobs.v2.positions.tracking_resolve import (
    resolve_tracking_url,
    tracking_urls_for_job,
)
from relocation_jobs.v2.users.history import append_status_event, status_history_for_job


def _base_result(company_name: str, job_url: str, country: str, **extra) -> dict:
    return {
        "company": company_name,
        "url": job_url,
        "country": country,
        "idempotency_key": job_idempotency_key(job_url),
        **extra,
    }


def _with_status_history(
    result: dict,
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
) -> dict:
    with db_transaction() as conn:
        history = status_history_for_job(conn, user_id, country, company_name, job_url)
    result["applied_history"] = history["applied"]
    result["applied_events"] = history.get("applied_events") or []
    result["rejected_history"] = history["rejected"]
    if history["applied"]:
        result["applied_date"] = max(history["applied"])
    if history["rejected"]:
        result["rejected_date"] = max(history["rejected"])
    return result


def set_applied(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    applied: bool,
    *,
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    preserved_lta = ""
    with db_transaction() as conn:
        storage_url = resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url,
        )
        if applied:
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    applied, applied_date, not_for_me, looking_to_apply, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 1, %s, 0, 0, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    applied = 1, applied_date = EXCLUDED.applied_date,
                    looking_to_apply = 0,
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    user_id, country, company_name, storage_url, (job_title or "").strip(),
                    now[:10], now,
                ),
            )
            append_status_event(
                conn, user_id, country, company_name, storage_url, "applied",
                event_date=now[:10],
            )
            row = conn.execute(
                """
                SELECT looking_to_apply_date FROM job_tracking
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (user_id, country, company_name, storage_url),
            ).fetchone()
            preserved_lta = (row or {}).get("looking_to_apply_date") or ""
        else:
            for url in tracking_urls_for_job(
                conn, user_id, country, company_name, canonical_url,
            ):
                conn.execute(
                    """
                    UPDATE job_tracking SET applied = 0, applied_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, url),
                )
    result = _base_result(company_name, storage_url, country, applied=applied)
    if applied:
        result["looking_to_apply"] = False
        if preserved_lta:
            result["looking_to_apply_date"] = preserved_lta
    return _with_status_history(result, user_id, country, company_name, storage_url)


def set_rejected(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    rejected: bool,
    *,
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        storage_url = resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url,
        )
        if rejected:
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    rejected, rejected_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    rejected = 1, rejected_date = EXCLUDED.rejected_date,
                    job_title = COALESCE(NULLIF(EXCLUDED.job_title, ''), job_tracking.job_title),
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    user_id, country, company_name, storage_url, (job_title or "").strip(),
                    now[:10], now,
                ),
            )
            append_status_event(
                conn, user_id, country, company_name, storage_url, "rejected",
                event_date=now[:10],
            )
        else:
            for url in tracking_urls_for_job(
                conn, user_id, country, company_name, canonical_url,
            ):
                conn.execute(
                    """
                    UPDATE job_tracking SET rejected = 0, rejected_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, url),
                )
    return _with_status_history(
        _base_result(company_name, storage_url, country, rejected=rejected),
        user_id, country, company_name, storage_url,
    )


def reapply(user_id: int, country: str, company_name: str, job_url: str) -> dict:
    return set_rejected(user_id, country, company_name, job_url, rejected=False)


def set_not_for_me(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    *,
    not_for_me: bool = True,
    reason: str | None = None,
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    date_only = now[:10]
    hide_reason = (reason or "not_for_me").strip() or "not_for_me"
    with db_transaction() as conn:
        storage_url = resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url,
        )
        if not_for_me:
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url,
                    not_for_me, not_for_me_date, not_for_me_reason, updated_at
                ) VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    not_for_me = 1, not_for_me_date = EXCLUDED.not_for_me_date,
                    not_for_me_reason = EXCLUDED.not_for_me_reason, updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, storage_url, date_only, hide_reason, now),
            )
            return _base_result(
                company_name, storage_url, country,
                not_for_me=True, not_for_me_date=date_only, not_for_me_reason=hide_reason,
            )
        for url in tracking_urls_for_job(
            conn, user_id, country, company_name, canonical_url,
        ):
            conn.execute(
                """
                UPDATE job_tracking
                SET not_for_me = 0, not_for_me_date = NULL, not_for_me_reason = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, url),
            )
    return _base_result(company_name, storage_url, country, not_for_me=False)


def set_looking_to_apply(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    looking_to_apply: bool,
    *,
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        storage_url = resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url,
        )
        if looking_to_apply:
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    looking_to_apply, looking_to_apply_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    looking_to_apply = 1, looking_to_apply_date = EXCLUDED.looking_to_apply_date,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    user_id, country, company_name, storage_url, (job_title or "").strip(),
                    now[:10], now,
                ),
            )
        else:
            for url in tracking_urls_for_job(
                conn, user_id, country, company_name, canonical_url,
            ):
                conn.execute(
                    """
                    UPDATE job_tracking
                    SET looking_to_apply = 0, looking_to_apply_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, url),
                )
    return _base_result(
        company_name, storage_url, country,
        looking_to_apply=looking_to_apply,
        looking_to_apply_date=now[:10] if looking_to_apply else "",
    )


def set_seen(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    seen: bool,
    *,
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        storage_url = resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url,
        )
        if seen:
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    seen, seen_date, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    seen = 1, seen_date = COALESCE(job_tracking.seen_date, EXCLUDED.seen_date),
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    user_id, country, company_name, storage_url, (job_title or "").strip(),
                    now[:10], now,
                ),
            )
        else:
            for url in tracking_urls_for_job(
                conn, user_id, country, company_name, canonical_url,
            ):
                conn.execute(
                    """
                    UPDATE job_tracking SET seen = 0, seen_date = NULL, updated_at = %s
                    WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                    """,
                    (now, user_id, country, company_name, url),
                )
    return _base_result(
        company_name, storage_url, country, seen=seen, seen_date=now[:10] if seen else "",
    )


def set_waiting_referral(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    waiting_referral: bool,
    *,
    linkedin_url: str = "",
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        storage_url = resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url,
        )
        if waiting_referral:
            if not linkedin_url.strip():
                raise ValueError("LinkedIn profile URL is required")
            conn.execute(
                """
                INSERT INTO job_tracking (
                    user_id, country, company_name, job_url, job_title,
                    waiting_referral, waiting_referral_date, referral_linkedin_url, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)
                ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                    waiting_referral = 1,
                    waiting_referral_date = EXCLUDED.waiting_referral_date,
                    referral_linkedin_url = EXCLUDED.referral_linkedin_url,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    user_id, country, company_name, storage_url, (job_title or "").strip(),
                    now[:10], linkedin_url.strip(), now,
                ),
            )
            return _base_result(
                company_name, storage_url, country,
                waiting_referral=True, waiting_referral_date=now[:10],
                referral_linkedin_url=linkedin_url.strip(),
            )
        for url in tracking_urls_for_job(
            conn, user_id, country, company_name, canonical_url,
        ):
            conn.execute(
                """
                UPDATE job_tracking
                SET waiting_referral = 0, waiting_referral_date = NULL,
                    referral_linkedin_url = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s AND job_url = %s
                """,
                (now, user_id, country, company_name, url),
            )
    return _base_result(company_name, storage_url, country, waiting_referral=False)


def set_ats_score(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    ats_score: int | None,
    *,
    job_title: str = "",
) -> dict:
    canonical_url = _normalize_url(job_url)
    now = _utc_now()
    with db_transaction() as conn:
        storage_url = resolve_tracking_url(
            conn, user_id, country, company_name, canonical_url,
        )
        conn.execute(
            """
            INSERT INTO job_tracking (
                user_id, country, company_name, job_url, job_title, ats_score, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, country, company_name, job_url) DO UPDATE SET
                ats_score = EXCLUDED.ats_score, updated_at = EXCLUDED.updated_at
            """,
            (
                user_id, country, company_name, storage_url, (job_title or "").strip(),
                ats_score, now,
            ),
        )
    return _base_result(company_name, storage_url, country, ats_score=ats_score)


def sync_company_applied(user_id: int, country: str, company_name: str) -> dict:
    now = _utc_now()
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt, MIN(applied_date) AS earliest
            FROM job_tracking
            WHERE user_id = %s AND country = %s AND company_name = %s AND applied = 1
            """,
            (user_id, country, company_name),
        ).fetchone()
        count = int((row or {}).get("cnt") or 0)
        if count > 0:
            applied_date = ((row or {}).get("earliest") or "").strip() or now[:10]
            conn.execute(
                """
                INSERT INTO company_tracking (
                    user_id, country, company_name, company_applied, company_applied_date, updated_at
                ) VALUES (%s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                    company_applied = 1, company_applied_date = EXCLUDED.company_applied_date,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, applied_date, now),
            )
            return {
                "company_applied": True, "company_applied_date": applied_date,
                "positions_applied": count, "company": company_name, "country": country,
            }
        conn.execute(
            """
            UPDATE company_tracking
            SET company_applied = 0, company_applied_date = NULL, updated_at = %s
            WHERE user_id = %s AND country = %s AND company_name = %s
            """,
            (now, user_id, country, company_name),
        )
    return {
        "company_applied": False, "company_applied_date": "",
        "positions_applied": 0, "company": company_name, "country": country,
    }


def set_company_awaiting_response(
    user_id: int,
    country: str,
    company_name: str,
    awaiting: bool,
    *,
    preserve_date: bool = False,
) -> dict:
    now = _utc_now()
    with db_transaction() as conn:
        if awaiting:
            date_only = now[:10]
            date_clause = (
                "awaiting_response_date = COALESCE(company_tracking.awaiting_response_date, EXCLUDED.awaiting_response_date)"
                if preserve_date else "awaiting_response_date = EXCLUDED.awaiting_response_date"
            )
            conn.execute(
                f"""
                INSERT INTO company_tracking (
                    user_id, country, company_name, awaiting_response, awaiting_response_date, updated_at
                ) VALUES (%s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                    awaiting_response = 1, {date_clause}, updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, date_only, now),
            )
        else:
            conn.execute(
                """
                UPDATE company_tracking
                SET awaiting_response = 0, awaiting_response_date = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s
                """,
                (now, user_id, country, company_name),
            )
    return {"company": company_name, "country": country, "awaiting_response": awaiting}


def load_wrong_location_hides(user_id: int, country_key: str | None = None) -> list[dict]:
    if country_key:
        rows = get_connection().execute(
            """
            SELECT country, company_name, job_url
            FROM job_tracking
            WHERE user_id = %s AND not_for_me = 1 AND not_for_me_reason = 'wrong_location'
              AND country = %s
            """,
            (user_id, country_key),
        ).fetchall()
    else:
        rows = get_connection().execute(
            """
            SELECT country, company_name, job_url
            FROM job_tracking
            WHERE user_id = %s AND not_for_me = 1 AND not_for_me_reason = 'wrong_location'
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]
