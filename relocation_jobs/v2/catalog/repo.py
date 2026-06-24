from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

from relocation_jobs.core.db import db_read, db_transaction
from relocation_jobs.core.job_identity import job_idempotency_key, stamp_job_identity
from relocation_jobs.core.location_tags import sync_company_location_fields

_COUNTRY_META_FIELDS = frozenset({
    "source", "fetched", "updated", "jobs_fetched", "total", "last_fetch_new_jobs",
})


def _row(row) -> dict:
    return dict(row) if row else {}


def _today_iso() -> str:
    return date.today().isoformat()


def _visa_from_db(raw) -> bool | None:
    if raw is None:
        return None
    return bool(raw)


def _visa_to_db(value) -> int | None:
    if value is True:
        return 1
    if value is False:
        return 0
    return None


def _json_column(value) -> str:
    if isinstance(value, list) and value:
        return json.dumps(value)
    return "[]"


def _job_locations_column(job: dict) -> str:
    locations = job.get("locations")
    if isinstance(locations, list) and locations:
        return json.dumps(locations)
    return "[]"


def _job_row(row) -> dict:
    data = _row(row)
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
    raw_locs = data.get("locations_json")
    if raw_locs and raw_locs != "[]":
        try:
            locs = json.loads(raw_locs) if isinstance(raw_locs, str) else raw_locs
            if isinstance(locs, list):
                job["locations"] = locs
        except json.JSONDecodeError:
            pass
    return job


def _company_row(row: dict, jobs: list[dict]) -> dict:
    return {
        "name": row["name"],
        "city": row.get("city") or "",
        "cities": [],
        "locations": [],
        "size": row.get("size") or "",
        "careers_url": row.get("careers_url") or "",
        "ats_type": row.get("ats_type") or "",
        "ats_url": row.get("ats_url") or "",
        "fetch_problem": bool(row.get("fetch_problem")),
        "fetch_problem_date": row.get("fetch_problem_date") or "",
        "fetch_ok": bool(row.get("fetch_ok")),
        "fetch_ok_date": row.get("fetch_ok_date") or "",
        "added": row.get("added") or "",
        "updated": row.get("updated") or "",
        "sources": [],
        "matching_jobs": jobs,
    }


def _load_country_from_db(country_key: str) -> dict | None:
    with db_read() as conn:
        meta_row = conn.execute(
            "SELECT * FROM country_meta WHERE country = %s",
            (country_key,),
        ).fetchone()
        if meta_row is None:
            return None
        meta = _row(meta_row)
        company_rows = conn.execute(
            "SELECT * FROM companies WHERE country = %s ORDER BY name",
            (country_key,),
        ).fetchall()
        ids = [int(_row(c)["id"]) for c in company_rows]
        jobs_by_id: dict[int, list[dict]] = defaultdict(list)
        if ids:
            for job_row in conn.execute(
                """
                SELECT * FROM matching_jobs
                WHERE company_id = ANY(%s)
                ORDER BY company_id, fetched DESC, title
                """,
                (ids,),
            ).fetchall():
                data = _row(job_row)
                jobs_by_id[int(data["company_id"])].append(_job_row(job_row))
        companies = [
            _company_row(_row(crow), jobs_by_id[int(_row(crow)["id"])])
            for crow in company_rows
        ]
    return {
        "source": meta.get("source") or "",
        "fetched": meta.get("fetched") or "",
        "updated": meta.get("updated") or "",
        "jobs_fetched": meta.get("jobs_fetched") or "",
        "total": meta.get("total") or len(companies),
        "last_fetch_new_jobs": int(meta.get("last_fetch_new_jobs") or 0),
        "companies": companies,
    }


def load_country_catalog(country_key: str) -> dict | None:
    return _load_country_from_db(country_key)


def get_company(country_key: str, company_name: str) -> dict | None:
    with db_read() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE country = %s AND lower(name) = lower(%s)",
            (country_key, company_name),
        ).fetchone()
        if row is None:
            return None
        data = _row(row)
        jobs = [
            _job_row(r)
            for r in conn.execute(
                "SELECT * FROM matching_jobs WHERE company_id = %s ORDER BY fetched DESC, title",
                (data["id"],),
            ).fetchall()
        ]
    return _company_row(data, jobs)


def get_job_by_url(
    job_url: str,
    *,
    company_name: str | None = None,
    country_key: str | None = None,
) -> dict | None:
    key = job_idempotency_key(job_url)
    if not key:
        return None
    sql = """
        SELECT j.title, j.url, j.idempotency_key, c.name AS company_name, c.country
        FROM matching_jobs j
        JOIN companies c ON c.id = j.company_id
        WHERE j.idempotency_key = %s
    """
    params: list = [key]
    if company_name:
        sql += " AND c.name = %s"
        params.append(company_name.strip())
    if country_key:
        sql += " AND c.country = %s"
        params.append(country_key.strip().lower())
    with db_read() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    return _row(row) or None


def _upsert_company_catalog_row(
    conn,
    country_key: str,
    company: dict,
    *,
    updated: str,
) -> int:
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
            _json_column(company.get("cities")),
            _json_column(company.get("locations")),
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
            _json_column(company.get("sources")),
        ),
    ).fetchone()
    return int(row["id"])


def _replace_company_job_rows(conn, company_id: int, full_board: list[dict]) -> None:
    board_keys: list[str] = []
    for job in full_board:
        stamp_job_identity(job)
        key = job.get("idempotency_key") or job_idempotency_key(job.get("url", ""))
        if not key:
            continue
        board_keys.append(key)
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
                _job_locations_column(job),
            ),
        )
    if board_keys:
        placeholders = ", ".join(["%s"] * len(board_keys))
        conn.execute(
            f"""
            DELETE FROM matching_jobs
            WHERE company_id = %s AND idempotency_key NOT IN ({placeholders})
            """,
            (company_id, *board_keys),
        )
    else:
        conn.execute("DELETE FROM matching_jobs WHERE company_id = %s", (company_id,))


def _patch_country_meta_on_conn(conn, country_key: str, **fields) -> None:
    updates = {k: v for k, v in fields.items() if k in _COUNTRY_META_FIELDS and v is not None}
    if not updates:
        return
    columns = ", ".join(f"{col} = %s" for col in updates)
    conn.execute(
        f"UPDATE country_meta SET {columns} WHERE country = %s",
        (*updates.values(), country_key),
    )


def patch_country_catalog_meta(country_key: str, **fields) -> None:
    with db_transaction() as conn:
        _patch_country_meta_on_conn(conn, country_key, **fields)


def sync_company_board_to_catalog(country_key: str, company: dict) -> None:
    updated = company.get("updated") or _today_iso()
    full_board = company.get("matching_jobs") or []
    with db_transaction() as conn:
        company_id = _upsert_company_catalog_row(conn, country_key, company, updated=updated)
        _replace_company_job_rows(conn, company_id, full_board)
        _patch_country_meta_on_conn(conn, country_key, updated=updated)
