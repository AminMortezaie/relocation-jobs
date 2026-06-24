from __future__ import annotations

import json
from datetime import date

from relocation_jobs.core.db import db_transaction
from relocation_jobs.core.job_identity import job_idempotency_key, stamp_job_identity
from relocation_jobs.core.location_tags import sync_company_location_fields


def _today() -> str:
    return date.today().isoformat()


def _visa_to_db(value) -> int | None:
    if value is True:
        return 1
    if value is False:
        return 0
    return None


def _json_list(value) -> str:
    if isinstance(value, list) and value:
        return json.dumps(value)
    return "[]"


def _job_locations_json(job: dict) -> str:
    locations = job.get("locations")
    if isinstance(locations, list) and locations:
        return json.dumps(locations)
    return "[]"


def _upsert_company_row(conn, country_key: str, company: dict, *, updated: str) -> int:
    name = (company.get("name") or "").strip()
    if not name:
        raise ValueError("company name is required")
    sync_company_location_fields(company, catalog_country=country_key)
    row = conn.execute(
        """
        INSERT INTO companies (
            country, name, city, cities_json, locations_json, size, careers_url,
            ats_type, ats_url, fetch_problem, fetch_problem_date, fetch_ok, fetch_ok_date,
            added, updated, sources_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (country, name) DO UPDATE SET
            city = EXCLUDED.city,
            cities_json = EXCLUDED.cities_json,
            locations_json = EXCLUDED.locations_json,
            size = EXCLUDED.size,
            careers_url = EXCLUDED.careers_url,
            ats_type = EXCLUDED.ats_type,
            ats_url = EXCLUDED.ats_url,
            fetch_problem = EXCLUDED.fetch_problem,
            fetch_problem_date = EXCLUDED.fetch_problem_date,
            fetch_ok = EXCLUDED.fetch_ok,
            fetch_ok_date = EXCLUDED.fetch_ok_date,
            updated = EXCLUDED.updated,
            sources_json = EXCLUDED.sources_json
        RETURNING id
        """,
        (
            country_key,
            name,
            company.get("city") or "",
            _json_list(company.get("cities")),
            _json_list(company.get("locations")),
            company.get("size") or "",
            company.get("careers_url") or "",
            company.get("ats_type") or "",
            company.get("ats_url") or "",
            1 if company.get("fetch_problem") else 0,
            company.get("fetch_problem_date"),
            1 if company.get("fetch_ok") else 0,
            company.get("fetch_ok_date"),
            company.get("added") or updated,
            company.get("updated") or updated,
            _json_list(company.get("sources")),
        ),
    ).fetchone()
    return int(row["id"])


def _sync_matching_jobs(conn, company_id: int, jobs: list[dict]) -> None:
    keys: list[str] = []
    for job in jobs:
        stamp_job_identity(job)
        key = job.get("idempotency_key") or job_idempotency_key(job.get("url", ""))
        if not key:
            continue
        keys.append(key)
        conn.execute(
            """
            INSERT INTO matching_jobs (
                company_id, idempotency_key, title, url, fetched, last_seen,
                visa_sponsorship, location, locations_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_id, idempotency_key) DO UPDATE SET
                title = EXCLUDED.title,
                url = EXCLUDED.url,
                fetched = EXCLUDED.fetched,
                last_seen = EXCLUDED.last_seen,
                visa_sponsorship = EXCLUDED.visa_sponsorship,
                location = COALESCE(NULLIF(EXCLUDED.location, ''), matching_jobs.location),
                locations_json = CASE
                    WHEN EXCLUDED.locations_json IS NOT NULL
                         AND EXCLUDED.locations_json != '[]'
                    THEN EXCLUDED.locations_json
                    ELSE matching_jobs.locations_json
                END
            """,
            (
                company_id,
                key,
                job.get("title") or "",
                job.get("url") or "",
                job.get("fetched") or "",
                job.get("last_seen") or job.get("fetched") or "",
                _visa_to_db(job.get("visa_sponsorship")),
                (job.get("location") or "").strip(),
                _job_locations_json(job),
            ),
        )
    if keys:
        placeholders = ", ".join(["%s"] * len(keys))
        conn.execute(
            f"""
            DELETE FROM matching_jobs
            WHERE company_id = %s AND idempotency_key NOT IN ({placeholders})
            """,
            (company_id, *keys),
        )
    else:
        conn.execute("DELETE FROM matching_jobs WHERE company_id = %s", (company_id,))


def touch_country_meta(country_key: str, **fields) -> None:
    allowed = {"source", "fetched", "updated", "jobs_fetched", "total", "last_fetch_new_jobs"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return
    columns = ", ".join(f"{col} = %s" for col in updates)
    with db_transaction() as conn:
        conn.execute(
            f"UPDATE country_meta SET {columns} WHERE country = %s",
            (*updates.values(), country_key),
        )


def save_company(country_key: str, company: dict) -> None:
    """Persist one company row and sync matching_jobs after scrape or manual edit."""
    updated = company.get("updated") or _today()
    with db_transaction() as conn:
        company_id = _upsert_company_row(conn, country_key, company, updated=updated)
        _sync_matching_jobs(conn, company_id, company.get("matching_jobs") or [])
    touch_country_meta(country_key, updated=updated)
