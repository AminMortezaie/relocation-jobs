from __future__ import annotations

from relocation_jobs.core.db import _utc_now, db_transaction, get_connection


def load_company_tracking(user_id: int) -> dict[tuple[str, str], dict]:
    rows = get_connection().execute(
        """
        SELECT country, company_name, company_applied, company_applied_date,
               awaiting_response, awaiting_response_date
        FROM company_tracking
        WHERE user_id = %s
        """,
        (user_id,),
    ).fetchall()
    return {(row["country"], row["company_name"]): row for row in rows}


def sync_company_applied_from_jobs_db(
    user_id: int,
    country: str,
    company_name: str,
) -> dict:
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
        count = int(row["cnt"] if row else 0)
        if count > 0:
            applied_date = (row["earliest"] or "").strip() or now[:10]
            conn.execute(
                """
                INSERT INTO company_tracking (
                    user_id, country, company_name,
                    company_applied, company_applied_date, updated_at
                ) VALUES (%s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                    company_applied = 1,
                    company_applied_date = EXCLUDED.company_applied_date,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, applied_date, now),
            )
            return {
                "company_applied": True,
                "company_applied_date": applied_date,
                "positions_applied": count,
                "company": company_name,
                "country": country,
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
        "company_applied": False,
        "company_applied_date": "",
        "positions_applied": 0,
        "company": company_name,
        "country": country,
    }


def set_company_applied_db(
    user_id: int,
    country: str,
    company_name: str,
    applied: bool,
) -> dict:
    now = _utc_now()
    with db_transaction() as conn:
        if applied:
            conn.execute(
                """
                INSERT INTO company_tracking (
                    user_id, country, company_name,
                    company_applied, company_applied_date, updated_at
                ) VALUES (%s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                    company_applied = 1,
                    company_applied_date = EXCLUDED.company_applied_date,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, now[:10], now),
            )
            applied_date = now[:10]
        else:
            conn.execute(
                """
                UPDATE company_tracking
                SET company_applied = 0, company_applied_date = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s
                """,
                (now, user_id, country, company_name),
            )
            applied_date = ""
    return {
        "company_applied": applied,
        "company_applied_date": applied_date if applied else "",
        "company": company_name,
        "country": country,
    }


def set_company_awaiting_response_db(
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
            if preserve_date:
                date_update_pg = (
                    "awaiting_response_date = COALESCE("
                    "company_tracking.awaiting_response_date, EXCLUDED.awaiting_response_date)"
                )
            else:
                date_update_pg = "awaiting_response_date = EXCLUDED.awaiting_response_date"
            conn.execute(
                f"""
                INSERT INTO company_tracking (
                    user_id, country, company_name,
                    awaiting_response, awaiting_response_date, updated_at
                ) VALUES (%s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, country, company_name) DO UPDATE SET
                    awaiting_response = 1,
                    {date_update_pg},
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, country, company_name, date_only, now),
            )
            row = conn.execute(
                """
                SELECT awaiting_response_date FROM company_tracking
                WHERE user_id = %s AND country = %s AND company_name = %s
                """,
                (user_id, country, company_name),
            ).fetchone()
            awaiting_date = ((row or {}).get("awaiting_response_date") or date_only)
        else:
            conn.execute(
                """
                UPDATE company_tracking
                SET awaiting_response = 0, awaiting_response_date = NULL, updated_at = %s
                WHERE user_id = %s AND country = %s AND company_name = %s
                """,
                (now, user_id, country, company_name),
            )
            awaiting_date = ""
    return {
        "awaiting_response": awaiting,
        "awaiting_response_date": awaiting_date if awaiting else "",
        "company": company_name,
        "country": country,
    }


def rename_company_tracking(country: str, old_name: str, new_name: str) -> None:
    with db_transaction() as conn:
        for table in ("job_status_events", "job_tracking", "company_tracking"):
            conn.execute(
                f"""
                UPDATE {table}
                SET company_name = %s
                WHERE country = %s AND company_name = %s
                """,
                (new_name, country, old_name),
            )


def clear_company_tracking(country: str, company_name: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            "DELETE FROM job_tracking WHERE country = %s AND company_name = %s",
            (country, company_name),
        )
        conn.execute(
            "DELETE FROM company_tracking WHERE country = %s AND company_name = %s",
            (country, company_name),
        )
