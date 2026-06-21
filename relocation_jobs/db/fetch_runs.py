"""Fetch run recording, listing, and one-time JSON data migration."""

from __future__ import annotations

from datetime import datetime

from relocation_jobs.db.core import db_transaction, get_connection


def tracking_is_empty() -> bool:
    row = get_connection().execute(
        """
        SELECT (SELECT COUNT(*) FROM job_tracking)
             + (SELECT COUNT(*) FROM company_tracking) AS n
        """
    ).fetchone()
    return int((row or {}).get("n", 0)) == 0


def _duration_seconds(started_at: str, finished_at: str) -> float | None:
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
        return max(0.0, (finish - start).total_seconds())
    except (ValueError, TypeError):
        return None


def _fetch_run_to_dict(row) -> dict:
    if not row:
        return {}
    company_name = (row.get("company_name") or "").strip() or None
    scope = (row.get("scope") or "").strip() or ("company" if company_name else "country")
    duration = row.get("duration_seconds")
    if duration is None:
        duration = _duration_seconds(row.get("started_at", ""), row.get("finished_at", ""))
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "country": row.get("country"),
        "company_name": company_name,
        "scope": scope,
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "duration_seconds": duration,
        "exit_code": row.get("exit_code"),
        "cancelled": bool(row.get("cancelled")),
        "new_jobs": int(row.get("new_jobs") or 0),
        "concurrency": row.get("concurrency"),
        "companies_done": row.get("companies_done"),
        "companies_total": row.get("companies_total"),
        "result_line": row.get("result_line"),
    }


def record_fetch_run(
    *,
    user_id: int,
    country: str,
    company_name: str | None,
    started_at: str,
    finished_at: str,
    exit_code: int | None,
    cancelled: bool = False,
    new_jobs: int = 0,
    concurrency: int | None = None,
    companies_done: int | None = None,
    companies_total: int | None = None,
    result_line: str | None = None,
) -> dict:
    company_name = (company_name or "").strip() or None
    scope = "company" if company_name else "country"
    duration = _duration_seconds(started_at, finished_at)
    params = (
        int(user_id),
        country,
        company_name,
        scope,
        started_at,
        finished_at,
        duration,
        exit_code,
        1 if cancelled else 0,
        int(new_jobs or 0),
        concurrency,
        companies_done,
        companies_total,
        (result_line or "").strip() or None,
    )
    with db_transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO fetch_runs (
                user_id, country, company_name, scope,
                started_at, finished_at, duration_seconds,
                exit_code, cancelled, new_jobs, concurrency,
                companies_done, companies_total, result_line
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            params,
        ).fetchone()
    return _fetch_run_to_dict(row)


def list_fetch_runs(
    user_id: int,
    *,
    country: str | None = None,
    limit: int = 20,
) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    sql = "SELECT * FROM fetch_runs WHERE user_id = %s"
    params: list = [int(user_id)]
    if country:
        sql += " AND country = %s"
        params.append(country)
    sql += f" ORDER BY started_at DESC, id DESC LIMIT {limit}"
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    return [_fetch_run_to_dict(row) for row in rows]


def list_all_fetch_runs(
    *,
    country: str | None = None,
    limit: int = 50,
) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    sql = """
        SELECT f.*, u.username
        FROM fetch_runs f
        JOIN users u ON u.id = f.user_id
        WHERE 1=1
    """
    params: list = []
    if country:
        sql += " AND f.country = %s"
        params.append(country)
    sql += f" ORDER BY f.started_at DESC, f.id DESC LIMIT {limit}"
    rows = get_connection().execute(sql, tuple(params)).fetchall()
    out: list[dict] = []
    for row in rows:
        data = _fetch_run_to_dict(row)
        data["username"] = row.get("username")
        out.append(data)
    return out


def migrate_tracking_from_json(user_id: int) -> int:
    from relocation_jobs.catalog_db import load_country as load_country_catalog
    from relocation_jobs.paths import COUNTRY_FILE_NAMES as COUNTRY_FILES
    from relocation_jobs.db.core import _normalize_url, _utc_now

    written = 0
    with db_transaction() as conn:
        for country_key in COUNTRY_FILES:
            data = load_country_catalog(country_key)
            if data is None:
                continue
            for company in data.get("companies", []):
                name = company.get("name", "")
                if not name:
                    continue
                if company.get("company_applied"):
                    conn.execute(
                        """
                        INSERT INTO company_tracking (
                            user_id, country, company_name,
                            company_applied, company_applied_date, updated_at
                        ) VALUES (%s, %s, %s, 1, %s, %s)
                        ON CONFLICT (user_id, country, company_name) DO NOTHING
                        """,
                        (
                            user_id,
                            country_key,
                            name,
                            company.get("company_applied_date") or _utc_now()[:10],
                            _utc_now(),
                        ),
                    )
                    written += 1
                for job in company.get("matching_jobs") or []:
                    url = _normalize_url(job.get("url", ""))
                    if not url:
                        continue
                    applied = bool(job.get("applied"))
                    not_for_me = bool(job.get("not_for_me"))
                    rejected = bool(job.get("rejected"))
                    if not applied and not not_for_me and not rejected:
                        continue
                    conn.execute(
                        """
                        INSERT INTO job_tracking (
                            user_id, country, company_name, job_url,
                            applied, applied_date, not_for_me, not_for_me_date,
                            rejected, rejected_date, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, country, company_name, job_url) DO NOTHING
                        """,
                        (
                            user_id,
                            country_key,
                            name,
                            url,
                            1 if applied else 0,
                            job.get("applied_date") if applied else None,
                            1 if not_for_me else 0,
                            job.get("not_for_me_date") if not_for_me else None,
                            1 if rejected else 0,
                            job.get("rejected_date") if rejected else None,
                            _utc_now(),
                        ),
                    )
                    written += 1
    return written
