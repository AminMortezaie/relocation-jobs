"""Catalog write operations."""

from __future__ import annotations

from relocation_jobs.core.db import db_transaction
from relocation_jobs.core.job_identity import job_idempotency_key, stamp_job_identity
from relocation_jobs.core.location_tags import sync_company_location_fields

from relocation_jobs.catalog.cache import invalidate_country_cache
from relocation_jobs.catalog.serialize import (
    cities_json_from_company,
    job_locations_json,
    json_sources,
    locations_json_from_company,
    row_dict,
)
from relocation_jobs.catalog.util import today, visa_to_db

def upsert_country_meta(conn, country_key: str, meta: dict) -> None:
    conn.execute(
        """
        INSERT INTO country_meta (
            country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (country) DO UPDATE SET
            source = EXCLUDED.source,
            fetched = EXCLUDED.fetched,
            updated = EXCLUDED.updated,
            jobs_fetched = EXCLUDED.jobs_fetched,
            total = EXCLUDED.total,
            last_fetch_new_jobs = EXCLUDED.last_fetch_new_jobs
        """,
        (
            country_key,
            meta.get("source") or "",
            meta.get("fetched") or "",
            meta.get("updated") or today(),
            meta.get("jobs_fetched") or "",
            meta.get("total") or 0,
            int(meta.get("last_fetch_new_jobs") or 0),
        ),
    )


def upsert_company_and_jobs(
    conn,
    country_key: str,
    company: dict,
    *,
    updated: str,
) -> None:
    """Upsert one company row and sync its matching_jobs (no full-country rewrite)."""
    name = (company.get("name") or "").strip()
    if not name:
        return

    added = company.get("added") or updated
    company_updated = company.get("updated") or updated
    sync_company_location_fields(company, catalog_country=country_key)
    cities_json = cities_json_from_company(company)
    locations_json = locations_json_from_company(company, catalog_country=country_key)
    city_display = company.get("city") or ""
    params = (
        country_key,
        name,
        city_display,
        cities_json,
        locations_json,
        company.get("size") or "",
        company.get("careers_url") or "",
        company.get("ats_type") or "",
        company.get("ats_url") or "",
        1 if company.get("fetch_problem") else 0,
        company.get("fetch_problem_date"),
        1 if company.get("fetch_ok") else 0,
        company.get("fetch_ok_date"),
        added,
        company_updated,
        json_sources(company),
    )

    cur = conn.execute(
        """
        INSERT INTO companies (
            country, name, city, cities_json, locations_json, size, careers_url, ats_type, ats_url,
            fetch_problem, fetch_problem_date, fetch_ok, fetch_ok_date,
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
        params,
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Failed to upsert company {name!r}")
    company_id = row["id"] if isinstance(row, dict) else row[0]

    jobs = company.get("matching_jobs") or []
    keys: list[str] = []
    job_rows: list[tuple] = []
    for job in jobs:
        stamp_job_identity(job)
        key = job.get("idempotency_key") or job_idempotency_key(job.get("url", ""))
        if not key:
            continue
        keys.append(key)
        job_rows.append((
            company_id,
            key,
            job.get("title") or "",
            job.get("url") or "",
            job.get("fetched") or "",
            job.get("last_seen") or job.get("fetched") or "",
            visa_to_db(job.get("visa_sponsorship")),
            (job.get("location") or "").strip(),
            job_locations_json(job),
        ))

    for row in job_rows:
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
            row,
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
        conn.execute(
            "DELETE FROM matching_jobs WHERE company_id = %s",
            (company_id,),
        )


def touch_country_meta(country_key: str, **fields) -> None:
    """Patch country_meta fields (e.g. updated, jobs_fetched) without rewriting companies."""
    allowed = {"source", "fetched", "updated", "jobs_fetched", "total", "last_fetch_new_jobs"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT * FROM country_meta WHERE country = %s",
            (country_key,),
        ).fetchone()
        if row is None:
            meta = {
                "source": "",
                "fetched": "",
                "updated": today(),
                "jobs_fetched": "",
                "total": 0,
                "last_fetch_new_jobs": 0,
            }
            meta.update(updates)
            upsert_country_meta(conn, country_key, meta)
        else:
            meta = row_dict(row)
            meta.update(updates)
            upsert_country_meta(conn, country_key, meta)
    invalidate_country_cache(country_key)


def upsert_company(country_key: str, company: dict, *, updated: str | None = None) -> None:
    """Write one company + jobs incrementally (fast path for scrape checkpoints)."""
    ts = updated or today()
    with db_transaction() as conn:
        upsert_company_and_jobs(conn, country_key, company, updated=ts)
    invalidate_country_cache(country_key)


def upsert_companies(
    country_key: str,
    companies: list[dict],
    *,
    updated: str | None = None,
    touch_meta: bool = True,
) -> None:
    """Batch upsert companies without deleting unrelated rows."""
    if not companies:
        return
    ts = updated or today()
    with db_transaction() as conn:
        for company in companies:
            upsert_company_and_jobs(conn, country_key, company, updated=ts)
        if touch_meta:
            count_row = conn.execute(
                "SELECT COUNT(*) AS n FROM companies WHERE country = %s",
                (country_key,),
            ).fetchone()
            total = int(row_dict(count_row).get("n", len(companies)))
            upsert_country_meta(conn, country_key, {
                "updated": ts,
                "jobs_fetched": ts,
                "total": total,
            })
    invalidate_country_cache(country_key)


def save_country_catalog(country_key: str, data: dict) -> None:
    """Sync country catalog: upsert all companies, remove ones absent from data."""
    companies = data.get("companies") or []
    meta = {
        "source": data.get("source") or "",
        "fetched": data.get("fetched") or "",
        "updated": data.get("updated") or today(),
        "jobs_fetched": data.get("jobs_fetched") or "",
        "total": data.get("total") or len(companies),
        "last_fetch_new_jobs": int(data.get("last_fetch_new_jobs") or 0),
    }
    names = [(company.get("name") or "").strip() for company in companies]
    names = [n for n in names if n]

    with db_transaction() as conn:
        upsert_country_meta(conn, country_key, meta)
        for company in companies:
            upsert_company_and_jobs(conn, country_key, company, updated=meta["updated"])

        if names:
            placeholders = ", ".join(["%s"] * len(names))
            conn.execute(
                f"""
                DELETE FROM companies
                WHERE country = %s AND name NOT IN ({placeholders})
                """,
                (country_key, *names),
            )
        else:
            conn.execute("DELETE FROM companies WHERE country = %s", (country_key,))
    invalidate_country_cache(country_key)


# ---------------------------------------------------------------------------
# Targeted single-row operations — used by company_service / job_service
# ---------------------------------------------------------------------------

def get_company(country_key: str, company_name: str) -> dict | None:
    """Fetch one company with its jobs; None if not found."""
    with db_read() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE country = %s AND lower(name) = lower(%s)",
            (country_key, company_name),
        ).fetchone()
        if row is None:
            return None
        cdata = row_dict(row)
        job_rows = conn.execute(
            "SELECT * FROM matching_jobs WHERE company_id = %s ORDER BY fetched DESC, title",
            (cdata["id"],),
        ).fetchall()
        jobs = [_job_row_to_dict(r) for r in job_rows]
    return _company_row_to_dict(cdata, jobs)


def get_job_by_url(job_url: str) -> dict | None:
    """Fetch one job row by URL idempotency key; returns title, url, company_name, country."""
    key = job_idempotency_key(job_url)
    if not key:
        return None
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT j.title, j.url, j.idempotency_key, c.name AS company_name, c.country
            FROM matching_jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.idempotency_key = %s
            """,
            (key,),
        ).fetchone()
    if row is None:
        return None
    return row_dict(row)


def rename_company_in_catalog(country_key: str, old_name: str, new_name: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            "UPDATE companies SET name = %s, updated = %s WHERE country = %s AND lower(name) = lower(%s)",
            (new_name, today(), country_key, old_name),
        )
    invalidate_country_cache(country_key)


def update_company_fields(country_key: str, company_name: str, **fields) -> None:
    """Patch arbitrary scalar columns for one company row."""
    allowed = {
        "careers_url", "ats_type", "ats_url",
        "city", "cities_json", "locations_json",
        "fetch_problem", "fetch_problem_date",
        "fetch_ok", "fetch_ok_date",
        "updated", "size",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{k} = %s" for k in updates)
    vals = list(updates.values())
    with db_transaction() as conn:
        conn.execute(
            f"UPDATE companies SET {cols} WHERE country = %s AND lower(name) = lower(%s)",
            (*vals, country_key, company_name),
        )
    invalidate_country_cache(country_key)


def update_company_location(
    country_key: str,
    company_name: str,
    locations: list[dict],
) -> None:
    """Recompute and persist all location-derived columns for one company."""
    temp: dict = {"locations": locations}
    sync_company_location_fields(temp, catalog_country=country_key)
    cities_json = cities_json_from_company(temp)
    locations_json = locations_json_from_company(temp, catalog_country=country_key)
    city = temp.get("city") or ""
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE companies
            SET city = %s, cities_json = %s, locations_json = %s, updated = %s
            WHERE country = %s AND lower(name) = lower(%s)
            """,
            (city, cities_json, locations_json, today(), country_key, company_name),
        )
    invalidate_country_cache(country_key)


def delete_company(country_key: str, company_name: str) -> bool:
    """Delete a company and its jobs (ON DELETE CASCADE). Returns True if found."""
    with db_transaction() as conn:
        cur = conn.execute(
            "DELETE FROM companies WHERE country = %s AND lower(name) = lower(%s) RETURNING id",
            (country_key, company_name),
        )
        deleted = cur.fetchone() is not None
    if deleted:
        invalidate_country_cache(country_key)
    return deleted


def insert_jobs(country_key: str, company_name: str, jobs: list[dict]) -> int:
    """Insert new jobs for a company, skipping duplicates. Returns count of new rows."""
    if not jobs:
        return 0
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT id FROM companies WHERE country = %s AND lower(name) = lower(%s)",
            (country_key, company_name),
        ).fetchone()
        if row is None:
            return 0
        company_id = row_dict(row)["id"]
        inserted = 0
        for job in jobs:
            stamp_job_identity(job)
            key = job.get("idempotency_key") or job_idempotency_key(job.get("url", ""))
            if not key:
                continue
            cur = conn.execute(
                """
                INSERT INTO matching_jobs (
                    company_id, idempotency_key, title, url, fetched, last_seen,
                    visa_sponsorship, location, locations_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    company_id, key,
                    job.get("title") or "",
                    job.get("url") or "",
                    job.get("fetched") or today(),
                    job.get("last_seen") or job.get("fetched") or today(),
                    visa_to_db(job.get("visa_sponsorship")),
                    (job.get("location") or "").strip(),
                    job_locations_json(job),
                ),
            )
            if cur.fetchone() is not None:
                inserted += 1
    if inserted:
        invalidate_country_cache(country_key)
    return inserted

