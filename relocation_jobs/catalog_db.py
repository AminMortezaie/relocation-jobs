"""Postgres catalog for companies and matching jobs."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from relocation_jobs.location_tags import (
    COUNTRY_LABELS,
    format_location_display,
    normalize_locations,
    sync_company_location_fields,
)
from relocation_jobs.db import db_read, db_transaction, get_connection
from relocation_jobs.job_identity import job_idempotency_key, stamp_job_identity
from relocation_jobs.paths import COUNTRY_FILE_NAMES


def _today() -> str:
    return date.today().isoformat()


def country_key_from_filename(name: str) -> str | None:
    m = re.match(r"(\w+)_companies\.json", Path(name).name)
    return m.group(1) if m else None


def _visa_to_db(value) -> int | None:
    if value is True:
        return 1
    if value is False:
        return 0
    return None


def _visa_from_db(value) -> bool | None:
    if value is None:
        return None
    return bool(value)


def init_catalog_schema() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS country_meta (
                country TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT '',
                fetched TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL DEFAULT '',
                jobs_fetched TEXT NOT NULL DEFAULT '',
                total INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                country TEXT NOT NULL,
                name TEXT NOT NULL,
                city TEXT NOT NULL DEFAULT '',
                size TEXT NOT NULL DEFAULT '',
                careers_url TEXT NOT NULL DEFAULT '',
                ats_type TEXT NOT NULL DEFAULT '',
                ats_url TEXT NOT NULL DEFAULT '',
                fetch_problem INTEGER NOT NULL DEFAULT 0,
                fetch_problem_date TEXT,
                added TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL DEFAULT '',
                sources_json TEXT NOT NULL DEFAULT '[]',
                UNIQUE(country, name)
            );

            CREATE TABLE IF NOT EXISTS matching_jobs (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                idempotency_key TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                fetched TEXT NOT NULL DEFAULT '',
                last_seen TEXT NOT NULL DEFAULT '',
                visa_sponsorship INTEGER,
                UNIQUE(company_id, idempotency_key)
            );

            CREATE INDEX IF NOT EXISTS idx_companies_country ON companies(country);
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON matching_jobs(company_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_idempotency ON matching_jobs(idempotency_key);
            """
        )
        _ensure_company_columns(conn)
        _ensure_job_columns(conn)
        _ensure_country_meta_columns(conn)


def _ensure_country_meta_columns(conn) -> None:
    conn.execute(
        "ALTER TABLE country_meta ADD COLUMN IF NOT EXISTS last_fetch_new_jobs INTEGER NOT NULL DEFAULT 0"
    )


def _ensure_company_columns(conn) -> None:
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS fetch_ok INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS fetch_ok_date TEXT"
    )
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS cities_json TEXT NOT NULL DEFAULT '[]'"
    )
    conn.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS locations_json TEXT NOT NULL DEFAULT '[]'"
    )


def _ensure_job_columns(conn) -> None:
    conn.execute(
        "ALTER TABLE matching_jobs ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE matching_jobs ADD COLUMN IF NOT EXISTS locations_json TEXT NOT NULL DEFAULT '[]'"
    )


def _job_locations_json(job: dict) -> str:
    locations = job.get("locations")
    if isinstance(locations, list) and locations:
        return json.dumps(locations)
    return "[]"


def _parse_job_locations_json(raw: str | None) -> list | None:
    if not raw or raw == "[]":
        return None
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return val if isinstance(val, list) and val else None


def catalog_has_data() -> bool:
    with db_read() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()
    data = _row_dict(row)
    return int(data.get("n") or 0) > 0


def _json_sources(company: dict) -> str:
    sources = company.get("sources")
    if isinstance(sources, list):
        return json.dumps(sources)
    return "[]"


def _parse_sources(raw: str) -> list:
    try:
        val = json.loads(raw or "[]")
        return val if isinstance(val, list) else []
    except json.JSONDecodeError:
        return []


def _parse_cities_json(raw: str | None) -> list[str]:
    try:
        val = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(val, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in val:
        label = (item or "").strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def _company_cities_from_row(data: dict) -> list[str]:
    cities = _parse_cities_json(data.get("cities_json"))
    if cities:
        return cities
    single = (data.get("city") or "").strip()
    return [single] if single else []


def _cities_json_from_company(company: dict) -> str:
    raw = company.get("cities")
    if isinstance(raw, list):
        cleaned = [(item or "").strip() for item in raw if (item or "").strip()]
    else:
        single = (company.get("city") or "").strip()
        cleaned = [single] if single else []
    seen: set[str] = set()
    unique: list[str] = []
    for label in cleaned:
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(label)
    unique.sort(key=lambda x: x.casefold())
    return json.dumps(unique)


def _parse_locations_json(raw: str | None, *, catalog_country: str = "") -> list[dict]:
    if raw:
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = []
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return normalize_locations(val, catalog_country=catalog_country)
    cities = _parse_cities_json(raw=None)
    if raw is None:
        cities = []
    return normalize_locations(None, catalog_country=catalog_country, legacy_cities=cities)


def _locations_json_from_company(company: dict, *, catalog_country: str = "") -> str:
    sync_company_location_fields(company, catalog_country=catalog_country)
    payload = [
        {"country": loc["country"], "city": loc["city"]}
        for loc in company.get("locations") or []
    ]
    return json.dumps(payload)


def _company_row_to_dict(row, jobs: list[dict]) -> dict:
    data = _row_dict(row)
    catalog_country = data.get("country") or ""
    locations = _parse_locations_json(
        data.get("locations_json"),
        catalog_country=catalog_country,
    )
    if not locations:
        locations = normalize_locations(
            None,
            catalog_country=catalog_country,
            legacy_cities=_parse_cities_json(data.get("cities_json")),
            legacy_city=data.get("city") or "",
        )
    company = {
        "name": data["name"],
        "city": " · ".join(
            format_location_display(loc["country"], loc["city"]) for loc in locations
        ),
        "cities": [loc["city"] for loc in locations],
        "locations": locations,
        "size": data.get("size") or "",
        "careers_url": data.get("careers_url") or "",
        "ats_type": data.get("ats_type") or "",
        "ats_url": data.get("ats_url") or "",
        "fetch_problem": bool(data.get("fetch_problem")),
        "fetch_problem_date": data.get("fetch_problem_date") or "",
        "fetch_ok": bool(data.get("fetch_ok")),
        "fetch_ok_date": data.get("fetch_ok_date") or "",
        "added": data.get("added") or "",
        "updated": data.get("updated") or "",
        "sources": _parse_sources(data.get("sources_json") or "[]"),
        "matching_jobs": jobs,
    }
    return company


def _row_dict(row) -> dict:
    if row is None:
        return {}
    return row if isinstance(row, dict) else dict(row)


def _job_row_to_dict(row) -> dict:
    data = _row_dict(row)
    job = {
        "title": data.get("title") or "",
        "url": data.get("url") or "",
        "fetched": data.get("fetched") or "",
        "last_seen": data.get("last_seen") or "",
        "idempotency_key": data.get("idempotency_key") or "",
        "visa_sponsorship": _visa_from_db(data.get("visa_sponsorship")),
    }
    location = (data.get("location") or "").strip()
    if location:
        job["location"] = location
    locations = _parse_job_locations_json(data.get("locations_json"))
    if locations:
        job["locations"] = locations
    return job


def load_country(country_key: str) -> dict | None:
    with db_read() as conn:
        meta_row = conn.execute(
            "SELECT * FROM country_meta WHERE country = %s",
            (country_key,),
        ).fetchone()
        if meta_row is None:
            return None

        meta = _row_dict(meta_row)

        companies_rows = conn.execute(
            "SELECT * FROM companies WHERE country = %s ORDER BY name",
            (country_key,),
        ).fetchall()

        company_ids = [_row_dict(crow)["id"] for crow in companies_rows]
        jobs_by_company: dict[int, list[dict]] = defaultdict(list)
        if company_ids:
            job_rows = conn.execute(
                """
                SELECT * FROM matching_jobs
                WHERE company_id = ANY(%s)
                ORDER BY company_id, fetched DESC, title
                """,
                (company_ids,),
            ).fetchall()
            for job_row in job_rows:
                jdata = _row_dict(job_row)
                jobs_by_company[int(jdata["company_id"])].append(_job_row_to_dict(job_row))

        companies: list[dict] = []
        for crow in companies_rows:
            cdata = _row_dict(crow)
            company_id = int(cdata["id"])
            companies.append(_company_row_to_dict(cdata, jobs_by_company[company_id]))

    return {
        "source": meta.get("source") or "",
        "fetched": meta.get("fetched") or "",
        "updated": meta.get("updated") or "",
        "jobs_fetched": meta.get("jobs_fetched") or "",
        "total": meta.get("total") or len(companies),
        "last_fetch_new_jobs": int(meta.get("last_fetch_new_jobs") or 0),
        "companies": companies,
    }


def _upsert_country_meta(conn, country_key: str, meta: dict) -> None:
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
            meta.get("updated") or _today(),
            meta.get("jobs_fetched") or "",
            meta.get("total") or 0,
            int(meta.get("last_fetch_new_jobs") or 0),
        ),
    )


def _upsert_company_and_jobs(
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
    cities_json = _cities_json_from_company(company)
    locations_json = _locations_json_from_company(company, catalog_country=country_key)
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
        _json_sources(company),
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
            _visa_to_db(job.get("visa_sponsorship")),
            (job.get("location") or "").strip(),
            _job_locations_json(job),
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
                "updated": _today(),
                "jobs_fetched": "",
                "total": 0,
                "last_fetch_new_jobs": 0,
            }
            meta.update(updates)
            _upsert_country_meta(conn, country_key, meta)
            return

        meta = _row_dict(row)
        meta.update(updates)
        _upsert_country_meta(conn, country_key, meta)


def upsert_company(country_key: str, company: dict, *, updated: str | None = None) -> None:
    """Write one company + jobs incrementally (fast path for scrape checkpoints)."""
    ts = updated or _today()
    with db_transaction() as conn:
        _upsert_company_and_jobs(conn, country_key, company, updated=ts)


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
    ts = updated or _today()
    with db_transaction() as conn:
        for company in companies:
            _upsert_company_and_jobs(conn, country_key, company, updated=ts)
        if touch_meta:
            count_row = conn.execute(
                "SELECT COUNT(*) AS n FROM companies WHERE country = %s",
                (country_key,),
            ).fetchone()
            total = int(_row_dict(count_row).get("n", len(companies)))
            _upsert_country_meta(conn, country_key, {
                "updated": ts,
                "jobs_fetched": ts,
                "total": total,
            })


def save_country(country_key: str, data: dict) -> None:
    """Sync country catalog: upsert all companies, remove ones absent from data."""
    companies = data.get("companies") or []
    meta = {
        "source": data.get("source") or "",
        "fetched": data.get("fetched") or "",
        "updated": data.get("updated") or _today(),
        "jobs_fetched": data.get("jobs_fetched") or "",
        "total": data.get("total") or len(companies),
        "last_fetch_new_jobs": int(data.get("last_fetch_new_jobs") or 0),
    }
    names = [(company.get("name") or "").strip() for company in companies]
    names = [n for n in names if n]

    with db_transaction() as conn:
        _upsert_country_meta(conn, country_key, meta)
        for company in companies:
            _upsert_company_and_jobs(conn, country_key, company, updated=meta["updated"])

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


# ---------------------------------------------------------------------------
# Catalog aggregation queries — used by services/admin_service.py
# Each function accepts an open connection so the caller controls the
# transaction boundary (typically a single db_read() context manager).
# ---------------------------------------------------------------------------

def query_company_stats_by_country(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            country,
            COUNT(*) AS companies,
            SUM(CASE WHEN fetch_problem = 1 THEN 1 ELSE 0 END) AS fetch_problems,
            SUM(CASE WHEN fetch_ok = 1 THEN 1 ELSE 0 END) AS fetch_ok,
            SUM(
                CASE
                    WHEN locations_json IS NULL OR locations_json IN ('', '[]')
                    THEN 1 ELSE 0
                END
            ) AS missing_locations
        FROM companies
        GROUP BY country
        ORDER BY country
        """
    ).fetchall()
    return [_row_dict(r) for r in rows]


def query_job_counts_by_country(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.country, COUNT(j.id) AS jobs,
               SUM(CASE WHEN j.visa_sponsorship = 1 THEN 1 ELSE 0 END) AS visa_jobs
        FROM companies c
        LEFT JOIN matching_jobs j ON j.company_id = c.id
        GROUP BY c.country
        """
    ).fetchall()
    return [_row_dict(r) for r in rows]


def query_empty_company_count(conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM (
            SELECT c.id
            FROM companies c
            LEFT JOIN matching_jobs j ON j.company_id = c.id
            GROUP BY c.id
            HAVING COUNT(j.id) = 0
        ) AS empty_companies_sub
        """
    ).fetchone()
    return int((_row_dict(row) or {}).get("n") or 0)


def query_ats_distribution(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(NULLIF(TRIM(ats_type), ''), '(unset)') AS ats_type,
            COUNT(*) AS companies
        FROM companies
        GROUP BY COALESCE(NULLIF(TRIM(ats_type), ''), '(unset)')
        ORDER BY companies DESC, ats_type ASC
        """
    ).fetchall()
    return [_row_dict(r) for r in rows]


def query_fetch_problem_companies(conn, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """
        SELECT country, name, fetch_problem_date, careers_url, ats_type
        FROM companies
        WHERE fetch_problem = 1
        ORDER BY fetch_problem_date DESC, name ASC
        LIMIT %s
        """,
        (int(limit),),
    ).fetchall()
    return [_row_dict(r) for r in rows]


def query_country_meta(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs
        FROM country_meta
        ORDER BY country
        """
    ).fetchall()
    return [_row_dict(r) for r in rows]


def load_catalog_stats() -> dict:
    """Run all 7 catalog aggregation queries in a single connection; return dict of results."""
    with db_read() as conn:
        return {
            "company_rows": query_company_stats_by_country(conn),
            "job_rows": query_job_counts_by_country(conn),
            "empty_companies": query_empty_company_count(conn),
            "ats_rows": query_ats_distribution(conn),
            "problem_rows": query_fetch_problem_companies(conn),
            "meta_rows": query_country_meta(conn),
            "latest_job_by_country": query_latest_job_fetches_by_country(conn),
        }


def query_latest_job_fetches_by_country(conn) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT
            c.country,
            MAX(COALESCE(NULLIF(j.last_seen, ''), NULLIF(j.fetched, ''))) AS latest_job_fetch
        FROM companies c
        LEFT JOIN matching_jobs j ON j.company_id = c.id
        GROUP BY c.country
        """
    ).fetchall()
    out: dict[str, str] = {}
    for row in rows:
        r = _row_dict(row)
        country = r.get("country")
        latest = (r.get("latest_job_fetch") or "").strip()
        if country and latest:
            out[country] = latest
    return out
