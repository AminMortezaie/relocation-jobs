from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

from relocation_jobs.core.db import db_read, db_transaction
from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    normalize_job_url,
    stamp_job_identity,
)
from relocation_jobs.core.location_tags import sync_company_location_fields

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
        "description_text": (data.get("description_text") or "").strip(),
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


def _job_row_with_context(row) -> dict:
    data = _row(row)
    job = _job_row(row)
    if data.get("company_name"):
        job["company_name"] = data["company_name"]
    if data.get("country"):
        job["country"] = data["country"]
    return job


_JOB_LOOKUP_COLUMNS = """
    j.title, j.url, j.idempotency_key, j.fetched, j.last_seen,
    j.visa_sponsorship, j.location, j.locations_json, j.description_text,
    c.name AS company_name, c.country
"""


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
        company_rows = conn.execute(
            "SELECT * FROM companies WHERE country = %s ORDER BY name",
            (country_key,),
        ).fetchall()
        if meta_row is None and not company_rows:
            return None
        meta = _row(meta_row) if meta_row is not None else {}
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


def load_country_meta(country_key: str) -> dict | None:
    with db_read() as conn:
        meta_row = conn.execute(
            "SELECT * FROM country_meta WHERE country = %s",
            (country_key,),
        ).fetchone()
        if meta_row is None:
            return None
        meta = _row(meta_row)
    return {
        "source": meta.get("source") or "",
        "fetched": meta.get("fetched") or "",
        "updated": meta.get("updated") or "",
        "jobs_fetched": meta.get("jobs_fetched") or "",
        "total": meta.get("total") or 0,
        "last_fetch_new_jobs": int(meta.get("last_fetch_new_jobs") or 0),
        "companies": [],
    }


def _catalog_company_filters(
    *,
    ats_type: str | None,
    search: str | None,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if ats_type == "generic":
        clauses.append(
            "(c.ats_type IS NULL OR TRIM(c.ats_type) = '' OR LOWER(TRIM(c.ats_type)) = 'generic')"
        )
    elif ats_type:
        clauses.append("LOWER(TRIM(c.ats_type)) = LOWER(%s)")
        params.append(ats_type)
    if search:
        pattern = f"%{search.strip().lower()}%"
        clauses.append(
            """(
                LOWER(c.name) LIKE %s
                OR LOWER(COALESCE(c.city, '')) LIKE %s
                OR EXISTS (
                    SELECT 1 FROM matching_jobs mj
                    WHERE mj.company_id = c.id AND LOWER(mj.title) LIKE %s
                )
            )"""
        )
        params.extend([pattern, pattern, pattern])
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def _country_in_clause(country_keys: list[str]) -> tuple[str, list[str]]:
    if not country_keys:
        return "FALSE", []
    placeholders = ", ".join("%s" for _ in country_keys)
    return f"c.country IN ({placeholders})", list(country_keys)


def count_catalog_companies(
    country_keys: list[str],
    *,
    ats_type: str | None = None,
    search: str | None = None,
) -> int:
    if not country_keys:
        return 0
    country_sql, country_params = _country_in_clause(country_keys)
    filter_sql, filter_params = _catalog_company_filters(ats_type=ats_type, search=search)
    with db_read() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM companies c
            WHERE {country_sql}{filter_sql}
            """,
            (*country_params, *filter_params),
        ).fetchone()
    return int(_row(row).get("total") or 0)


def count_fetch_problems(country_keys: list[str]) -> int:
    if not country_keys:
        return 0
    country_sql, country_params = _country_in_clause(country_keys)
    with db_read() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM companies c
            WHERE {country_sql} AND COALESCE(c.fetch_problem, 0) <> 0
            """,
            tuple(country_params),
        ).fetchone()
    return int(_row(row).get("total") or 0)


def load_catalog_companies_page(
    country_keys: list[str],
    *,
    offset: int,
    limit: int,
    ats_type: str | None = None,
    search: str | None = None,
) -> list[tuple[str, dict]]:
    if not country_keys or limit <= 0:
        return []
    country_sql, country_params = _country_in_clause(country_keys)
    filter_sql, filter_params = _catalog_company_filters(ats_type=ats_type, search=search)
    with db_read() as conn:
        company_rows = conn.execute(
            f"""
            SELECT c.*
            FROM companies c
            WHERE {country_sql}{filter_sql}
            ORDER BY c.country, c.name
            LIMIT %s OFFSET %s
            """,
            (*country_params, *filter_params, limit, max(offset, 0)),
        ).fetchall()
        if not company_rows:
            return []
        ids = [int(_row(c)["id"]) for c in company_rows]
        jobs_by_id: dict[int, list[dict]] = defaultdict(list)
        id_placeholders = ", ".join("%s" for _ in ids)
        for job_row in conn.execute(
            f"""
            SELECT * FROM matching_jobs
            WHERE company_id IN ({id_placeholders})
            ORDER BY company_id, fetched DESC, title
            """,
            tuple(ids),
        ).fetchall():
            data = _row(job_row)
            jobs_by_id[int(data["company_id"])].append(_job_row(job_row))
    out: list[tuple[str, dict]] = []
    for crow in company_rows:
        data = _row(crow)
        country_key = data["country"]
        company = _company_row(data, jobs_by_id[int(data["id"])])
        sync_company_location_fields(company, catalog_country=country_key)
        out.append((country_key, company))
    return out


def list_country_company_stubs(country_key: str) -> list[dict]:
    with db_read() as conn:
        rows = conn.execute(
            """
            SELECT c.name, c.ats_type,
                   EXISTS (
                       SELECT 1 FROM matching_jobs mj WHERE mj.company_id = c.id
                   ) AS has_jobs
            FROM companies c
            WHERE c.country = %s
            ORDER BY c.name
            """,
            (country_key,),
        ).fetchall()
    if not rows:
        return []
    return [
        {
            "name": _row(row)["name"],
            "ats_type": (_row(row).get("ats_type") or "").strip(),
            "has_jobs": bool(_row(row).get("has_jobs")),
        }
        for row in rows
    ]


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
    norm = normalize_job_url(job_url)
    key = job_idempotency_key(job_url)
    if not norm and not key:
        return None
    if company_name and country_key and key:
        with db_read() as conn:
            row = conn.execute(
                f"""
                SELECT {_JOB_LOOKUP_COLUMNS}
                FROM matching_jobs j
                JOIN companies c ON c.id = j.company_id
                WHERE c.country = %s AND c.name = %s
                  AND (j.idempotency_key = %s OR j.url = %s)
                LIMIT 1
                """,
                (country_key.strip().lower(), company_name.strip(), key, job_url.strip()),
            ).fetchone()
            if row is not None:
                return _job_row_with_context(row)
    sql = f"""
        SELECT {_JOB_LOOKUP_COLUMNS}
        FROM matching_jobs j
        JOIN companies c ON c.id = j.company_id
        WHERE 1=1
    """
    params: list = []
    if company_name:
        sql += " AND c.name = %s"
        params.append(company_name.strip())
    if country_key:
        sql += " AND c.country = %s"
        params.append(country_key.strip().lower())
    with db_read() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    for row in rows:
        if norm and normalize_job_url(row.get("url", "")) == norm:
            return _job_row_with_context(row)
    if key:
        for row in rows:
            if (row.get("idempotency_key") or "") == key:
                return _job_row_with_context(row)
        for row in rows:
            if job_idempotency_key(row.get("url", "")) == key:
                return _job_row_with_context(row)
    return None


def get_job_by_idempotency_key(idempotency_key: str) -> dict | None:
    key = (idempotency_key or "").strip()
    if not key:
        return None
    with db_read() as conn:
        row = conn.execute(
            f"""
            SELECT {_JOB_LOOKUP_COLUMNS}
            FROM matching_jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.idempotency_key = %s
            LIMIT 1
            """,
            (key,),
        ).fetchone()
    if row is None:
        return None
    return _job_row_with_context(row)


def update_job_description_text(idempotency_key: str, description_text: str) -> bool:
    key = (idempotency_key or "").strip()
    if not key:
        return False
    with db_transaction() as conn:
        row = conn.execute(
            """
            UPDATE matching_jobs
            SET description_text = %s
            WHERE idempotency_key = %s
            RETURNING id
            """,
            ((description_text or "").strip(), key),
        ).fetchone()
    return row is not None


def update_matching_job_fields(
    country_key: str,
    company_name: str,
    *,
    lookup_url: str = "",
    idempotency_key: str = "",
    title: str | None = None,
    url: str | None = None,
    location: str | None = None,
    description_text: str | None = None,
    posted_at: str | None = None,
) -> dict | None:
    from relocation_jobs.catalog.cache import invalidate_country_cache

    country = (country_key or "").strip().lower()
    company = (company_name or "").strip()
    if not country or not company:
        raise ValueError("country and company are required")

    lookup_key = (idempotency_key or "").strip()
    if not lookup_key:
        lookup_key = job_idempotency_key(lookup_url)
    if not lookup_key:
        raise ValueError("url or idempotency_key is required")

    sets: list[str] = []
    params: list = []

    if title is not None:
        sets.append("title = %s")
        params.append((title or "").strip())
    if location is not None:
        sets.append("location = %s")
        params.append((location or "").strip())
    if description_text is not None:
        sets.append("description_text = %s")
        params.append((description_text or "").strip())
    if posted_at is not None:
        stamp = (posted_at or "").strip()
        sets.append("fetched = %s")
        params.append(stamp)
        sets.append("last_seen = %s")
        params.append(stamp)
    if url is not None:
        normalized = normalize_job_url(url)
        if not normalized:
            raise ValueError("url is invalid")
        identity = stamp_job_identity({"url": normalized})
        new_key = (identity.get("idempotency_key") or "").strip()
        if not new_key:
            raise ValueError("url is invalid")
        sets.append("url = %s")
        params.append(normalized)
        sets.append("idempotency_key = %s")
        params.append(new_key)
        lookup_key_for_return = new_key
    else:
        lookup_key_for_return = lookup_key

    if not sets:
        raise ValueError("at least one field to update is required")

    with db_transaction() as conn:
        company_row = conn.execute(
            "SELECT id FROM companies WHERE country = %s AND lower(name) = lower(%s)",
            (country, company),
        ).fetchone()
        if company_row is None:
            return None
        company_id = _row(company_row)["id"]
        params.extend([company_id, lookup_key])
        row = conn.execute(
            f"""
            UPDATE matching_jobs
            SET {", ".join(sets)}
            WHERE company_id = %s AND idempotency_key = %s
            RETURNING idempotency_key, title, url, location, description_text
            """,
            tuple(params),
        ).fetchone()
    if row is None:
        return None
    invalidate_country_cache(country)
    updated = _row(row)
    return get_job_by_url(
        updated.get("url") or lookup_url,
        company_name=company,
        country_key=country,
    ) or {
        **updated,
        "company_name": company,
        "country": country,
        "idempotency_key": updated.get("idempotency_key") or lookup_key_for_return,
    }


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
                visa_sponsorship, location, locations_json, description_text
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                END,
                description_text = CASE
                    WHEN EXCLUDED.description_text IS NOT NULL
                         AND EXCLUDED.description_text != ''
                    THEN EXCLUDED.description_text
                    ELSE matching_jobs.description_text
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
                (job.get("description_text") or "").strip(),
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
    from relocation_jobs.catalog.writes import ensure_country_meta

    ensure_country_meta(conn, country_key, **fields)


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
