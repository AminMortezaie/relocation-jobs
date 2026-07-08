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
from relocation_jobs.core.location_tags import country_label, sync_company_location_fields

from relocation_jobs.catalog.cache import invalidate_country_cache
from relocation_jobs.catalog.serialize import (
    cities_json_from_company,
    job_locations_json,
    json_sources,
    locations_json_from_company,
)

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


def _job_stats_row(row) -> dict:
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


_JOB_LIST_COLUMNS = """
    title, url, idempotency_key, fetched, last_seen,
    visa_sponsorship, location, locations_json, company_id
"""

_JOB_LIST_COLUMNS_J = """
    j.title, j.url, j.idempotency_key, j.fetched, j.last_seen,
    j.visa_sponsorship, j.location, j.locations_json, j.company_id
"""

_JOB_LIST_COLUMNS_J_WITH_DESC = """
    j.title, j.url, j.idempotency_key, j.fetched, j.last_seen,
    j.visa_sponsorship, j.location, j.locations_json, j.description_text,
    j.company_id
"""


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


def load_catalog_for_countries(
    country_keys: list[str],
    *,
    include_descriptions: bool = True,
    ats_type: str | None = None,
    search: str | None = None,
) -> dict[str, dict]:
    keys = [key for key in country_keys if key]
    if not keys:
        return {}
    country_sql, country_params = _country_in_clause(keys)
    filter_sql, filter_params = _catalog_company_filters(ats_type=ats_type, search=search)
    job_columns_sql = _JOB_LIST_COLUMNS_J_WITH_DESC if include_descriptions else _JOB_LIST_COLUMNS_J
    job_row_fn = _job_row if include_descriptions else _job_stats_row
    with db_read() as conn:
        meta_rows = conn.execute(
            f"SELECT * FROM country_meta WHERE {country_sql.replace('c.country', 'country')}",
            tuple(country_params),
        ).fetchall()
        company_rows = conn.execute(
            f"""
            SELECT c.* FROM companies c
            WHERE {country_sql}{filter_sql}
            ORDER BY c.country, c.name
            """,
            (*country_params, *filter_params),
        ).fetchall()
        ids = [int(_row(crow)["id"]) for crow in company_rows]
        jobs_by_id: dict[int, list[dict]] = defaultdict(list)
        if ids:
            for job_row in conn.execute(
                f"""
                SELECT {job_columns_sql}
                FROM matching_jobs j
                WHERE j.company_id = ANY(%s)
                ORDER BY j.company_id, j.fetched DESC, j.title
                """,
                (ids,),
            ).fetchall():
                data = _row(job_row)
                jobs_by_id[int(data["company_id"])].append(job_row_fn(job_row))

    meta_by_country = {
        _row(row)["country"]: _row(row)
        for row in meta_rows
    }
    companies_by_country: dict[str, list[dict]] = defaultdict(list)
    for crow in company_rows:
        company = _row(crow)
        country = company["country"]
        sync_company_location_fields(company, catalog_country=country)
        companies_by_country[country].append(
            _company_row(company, jobs_by_id[int(company["id"])])
        )

    out: dict[str, dict] = {}
    for country in keys:
        meta = meta_by_country.get(country, {})
        companies = companies_by_country.get(country, [])
        if not meta and not companies:
            continue
        out[country] = {
            "source": meta.get("source") or "",
            "fetched": meta.get("fetched") or "",
            "updated": meta.get("updated") or "",
            "jobs_fetched": meta.get("jobs_fetched") or "",
            "total": meta.get("total") or len(companies),
            "last_fetch_new_jobs": int(meta.get("last_fetch_new_jobs") or 0),
            "companies": companies,
        }
    return out


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


def load_company_location_sources(country_keys: list[str]) -> list[dict]:
    if not country_keys:
        return []
    country_sql, country_params = _country_in_clause(country_keys)
    with db_read() as conn:
        rows = conn.execute(
            f"""
            SELECT c.country, c.city, c.cities_json, c.locations_json
            FROM companies c
            WHERE {country_sql}
            """,
            tuple(country_params),
        ).fetchall()
    return [_row(row) for row in rows]


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
            SELECT {_JOB_LIST_COLUMNS}
            FROM matching_jobs
            WHERE company_id IN ({id_placeholders})
            ORDER BY company_id, fetched DESC, title
            """,
            tuple(ids),
        ).fetchall():
            data = _row(job_row)
            jobs_by_id[int(data["company_id"])].append(_job_stats_row(job_row))
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


def _upsert_country_meta_row(conn, country_key: str, meta: dict) -> None:
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
            meta.get("updated") or _today_iso(),
            meta.get("jobs_fetched") or "",
            meta.get("total") or 0,
            int(meta.get("last_fetch_new_jobs") or 0),
        ),
    )


def _ensure_country_meta(conn, country_key: str, **fields) -> None:
    allowed = {"source", "fetched", "updated", "jobs_fetched", "total", "last_fetch_new_jobs"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    row = conn.execute(
        "SELECT * FROM country_meta WHERE country = %s",
        (country_key,),
    ).fetchone()
    if row is None:
        meta = {
            "source": "",
            "fetched": "",
            "updated": _today_iso(),
            "jobs_fetched": "",
            "total": 0,
            "last_fetch_new_jobs": 0,
        }
        meta.update(updates)
        _upsert_country_meta_row(conn, country_key, meta)
        return
    if not updates:
        return
    meta = _row(row)
    meta.update(updates)
    _upsert_country_meta_row(conn, country_key, meta)


def _patch_country_meta_on_conn(conn, country_key: str, **fields) -> None:
    _ensure_country_meta(conn, country_key, **fields)


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


def _upsert_company_row_on_conn(
    conn,
    country_key: str,
    company: dict,
    *,
    updated: str,
) -> int:
    name = (company.get("name") or "").strip()
    added = company.get("added") or updated
    company_updated = company.get("updated") or updated
    sync_company_location_fields(company, catalog_country=country_key)
    params = (
        country_key,
        name,
        company.get("city") or "",
        cities_json_from_company(company),
        locations_json_from_company(company, catalog_country=country_key),
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
    return row["id"] if isinstance(row, dict) else row[0]


def _merge_matching_jobs_on_conn(conn, company_id: int, jobs: list[dict]) -> None:
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
            job_locations_json(job),
            (job.get("description_text") or "").strip(),
        ))

    for row in job_rows:
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


def upsert_company_and_jobs(
    conn,
    country_key: str,
    company: dict,
    *,
    updated: str,
) -> None:
    name = (company.get("name") or "").strip()
    if not name:
        return
    company_id = _upsert_company_row_on_conn(
        conn, country_key, company, updated=updated,
    )
    _merge_matching_jobs_on_conn(conn, company_id, company.get("matching_jobs") or [])


def upsert_company(country_key: str, company: dict, *, updated: str | None = None) -> None:
    ts = updated or _today_iso()
    with db_transaction() as conn:
        upsert_company_and_jobs(conn, country_key, company, updated=ts)
        count_row = conn.execute(
            "SELECT COUNT(*) AS n FROM companies WHERE country = %s",
            (country_key,),
        ).fetchone()
        total = int(_row(count_row).get("n") or 0)
        _ensure_country_meta(conn, country_key, updated=ts, total=total)
    invalidate_country_cache(country_key)


def upsert_companies(
    country_key: str,
    companies: list[dict],
    *,
    updated: str | None = None,
    touch_meta: bool = True,
) -> None:
    if not companies:
        return
    ts = updated or _today_iso()
    with db_transaction() as conn:
        for company in companies:
            upsert_company_and_jobs(conn, country_key, company, updated=ts)
        if touch_meta:
            count_row = conn.execute(
                "SELECT COUNT(*) AS n FROM companies WHERE country = %s",
                (country_key,),
            ).fetchone()
            total = int(_row(count_row).get("n", len(companies)))
            _upsert_country_meta_row(conn, country_key, {
                "updated": ts,
                "jobs_fetched": ts,
                "total": total,
            })
    invalidate_country_cache(country_key)


def sync_country_catalog(country_key: str, data: dict) -> None:
    companies = data.get("companies") or []
    meta = {
        "source": data.get("source") or "",
        "fetched": data.get("fetched") or "",
        "updated": data.get("updated") or _today_iso(),
        "jobs_fetched": data.get("jobs_fetched") or "",
        "total": data.get("total") or len(companies),
        "last_fetch_new_jobs": int(data.get("last_fetch_new_jobs") or 0),
    }
    names = [(company.get("name") or "").strip() for company in companies]
    names = [n for n in names if n]

    with db_transaction() as conn:
        _upsert_country_meta_row(conn, country_key, meta)
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


def rename_company_in_catalog(country_key: str, old_name: str, new_name: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            "UPDATE companies SET name = %s, updated = %s WHERE country = %s AND lower(name) = lower(%s)",
            (new_name, _today_iso(), country_key, old_name),
        )
    invalidate_country_cache(country_key)


def update_company_fields(country_key: str, company_name: str, **fields) -> None:
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
            (city, cities_json, locations_json, _today_iso(), country_key, company_name),
        )
    invalidate_country_cache(country_key)


def delete_company(country_key: str, company_name: str) -> bool:
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
    if not jobs:
        return 0
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT id FROM companies WHERE country = %s AND lower(name) = lower(%s)",
            (country_key, company_name),
        ).fetchone()
        if row is None:
            return 0
        company_id = _row(row)["id"]
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
                    visa_sponsorship, location, locations_json, description_text
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    company_id, key,
                    job.get("title") or "",
                    job.get("url") or "",
                    job.get("fetched") or _today_iso(),
                    job.get("last_seen") or job.get("fetched") or _today_iso(),
                    _visa_to_db(job.get("visa_sponsorship")),
                    (job.get("location") or "").strip(),
                    job_locations_json(job),
                    (job.get("description_text") or "").strip(),
                ),
            )
            if cur.fetchone() is not None:
                inserted += 1
    if inserted:
        invalidate_country_cache(country_key)
    return inserted


def _query_company_stats_by_country(conn) -> list[dict]:
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
    return [_row(r) for r in rows]


def _query_job_counts_by_country(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.country, COUNT(j.id) AS jobs,
               SUM(CASE WHEN j.visa_sponsorship = 1 THEN 1 ELSE 0 END) AS visa_jobs
        FROM companies c
        LEFT JOIN matching_jobs j ON j.company_id = c.id
        GROUP BY c.country
        """
    ).fetchall()
    return [_row(r) for r in rows]


def _query_empty_company_count(conn) -> int:
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
    return int((_row(row) or {}).get("n") or 0)


def _query_ats_distribution(conn) -> list[dict]:
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
    return [_row(r) for r in rows]


def _query_fetch_problem_companies(conn, limit: int = 100) -> list[dict]:
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
    return [_row(r) for r in rows]


def _query_country_meta(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs
        FROM country_meta
        ORDER BY country
        """
    ).fetchall()
    return [_row(r) for r in rows]


def _query_latest_job_fetches_by_country(conn) -> dict[str, str]:
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
        data = _row(row)
        country = data.get("country")
        latest = (data.get("latest_job_fetch") or "").strip()
        if country and latest:
            out[country] = latest
    return out


def catalog_has_data() -> bool:
    with db_read() as conn:
        row = conn.execute("SELECT 1 FROM companies LIMIT 1").fetchone()
    return row is not None


def load_catalog_stats() -> dict:
    with db_read() as conn:
        return {
            "company_rows": _query_company_stats_by_country(conn),
            "job_rows": _query_job_counts_by_country(conn),
            "empty_companies": _query_empty_company_count(conn),
            "ats_rows": _query_ats_distribution(conn),
            "problem_rows": _query_fetch_problem_companies(conn),
            "meta_rows": _query_country_meta(conn),
            "latest_job_by_country": _query_latest_job_fetches_by_country(conn),
        }


def _normalize_ts_for_sort(ts: str) -> str:
    value = (ts or "").strip()
    if not value:
        return "0000-00-00T00:00:00"
    if len(value) == 10 and value[4] == "-":
        return f"{value}T00:00:00"
    return value.replace("Z", "+00:00")


def _max_timestamp(*values: str | None) -> str:
    candidates = [(v or "").strip() for v in values if (v or "").strip()]
    if not candidates:
        return ""
    return max(candidates, key=_normalize_ts_for_sort)


def _empty_catalog_overview() -> dict:
    return {
        "has_data": False,
        "countries": [],
        "totals": {
            "companies": 0,
            "jobs": 0,
            "stored_jobs": 0,
            "visa_jobs": 0,
            "stored_visa_jobs": 0,
            "fetch_problems": 0,
            "fetch_ok": 0,
            "empty_companies": 0,
            "missing_locations": 0,
        },
        "by_ats": [],
        "fetch_problem_companies": [],
        "country_meta": [],
    }


def _overview_jobs_by_country(job_rows: list[dict]) -> dict[str, dict]:
    return {
        row["country"]: {
            "stored_jobs": int(row.get("jobs") or 0),
            "stored_visa_jobs": int(row.get("visa_jobs") or 0),
        }
        for row in job_rows
    }


def _overview_country_rows(
    company_rows: list[dict],
    jobs_by_country: dict[str, dict],
    empty_companies: int,
) -> tuple[list[dict], dict]:
    countries: list[dict] = []
    totals = {
        "companies": 0,
        "jobs": 0,
        "stored_jobs": 0,
        "visa_jobs": 0,
        "stored_visa_jobs": 0,
        "fetch_problems": 0,
        "fetch_ok": 0,
        "empty_companies": empty_companies,
        "missing_locations": 0,
    }
    for row in company_rows:
        country = row["country"]
        stored = jobs_by_country.get(country, {"stored_jobs": 0, "stored_visa_jobs": 0})
        companies_count = int(row.get("companies") or 0)
        stored_jobs = int(stored.get("stored_jobs") or 0)
        stored_visa = int(stored.get("stored_visa_jobs") or 0)
        countries.append({
            "country": country,
            "label": country_label(country),
            "companies": companies_count,
            "jobs": stored_jobs,
            "visa_jobs": stored_visa,
            "fetch_problems": int(row.get("fetch_problems") or 0),
            "fetch_ok": int(row.get("fetch_ok") or 0),
            "missing_locations": int(row.get("missing_locations") or 0),
        })
        totals["companies"] += companies_count
        totals["stored_jobs"] += stored_jobs
        totals["stored_visa_jobs"] += stored_visa
        totals["jobs"] += stored_jobs
        totals["visa_jobs"] += stored_visa
        totals["fetch_problems"] += int(row.get("fetch_problems") or 0)
        totals["fetch_ok"] += int(row.get("fetch_ok") or 0)
        totals["missing_locations"] += int(row.get("missing_locations") or 0)
    countries.sort(key=lambda row: row["country"])
    return countries, totals


def _overview_country_meta(
    meta_rows: list[dict],
    latest_job_by_country: dict[str, str],
    countries: list[dict],
) -> list[dict]:
    companies_by_country = {c["country"]: c["companies"] for c in countries}
    meta_by_country: dict[str, dict] = {}
    for row in meta_rows:
        country = row.get("country", "")
        last_fetch = _max_timestamp(
            row.get("jobs_fetched"),
            latest_job_by_country.get(country),
        )
        meta_by_country[country] = {
            "country": country,
            "label": country_label(country or ""),
            "source": row.get("source"),
            "catalog_imported": row.get("fetched"),
            "last_fetch": last_fetch,
            "updated": row.get("updated"),
            "jobs_fetched": row.get("jobs_fetched"),
            "total": companies_by_country.get(country, int(row.get("total") or 0)),
            "last_fetch_new_jobs": int(row.get("last_fetch_new_jobs") or 0),
        }

    for country_row in countries:
        country = country_row["country"]
        if country in meta_by_country:
            continue
        meta_by_country[country] = {
            "country": country,
            "label": country_row["label"],
            "source": "",
            "catalog_imported": "",
            "last_fetch": latest_job_by_country.get(country, ""),
            "updated": "",
            "jobs_fetched": "",
            "total": country_row["companies"],
            "last_fetch_new_jobs": 0,
        }
    return sorted(meta_by_country.values(), key=lambda row: row["country"])


def get_catalog_overview() -> dict:
    if not catalog_has_data():
        return _empty_catalog_overview()

    stats = load_catalog_stats()
    jobs_by_country = _overview_jobs_by_country(stats["job_rows"])
    countries, totals = _overview_country_rows(
        stats["company_rows"],
        jobs_by_country,
        stats["empty_companies"],
    )
    by_ats = [
        {"ats_type": row["ats_type"], "companies": int(row.get("companies") or 0)}
        for row in stats["ats_rows"]
    ]
    fetch_problem_companies = [
        {
            "country": row.get("country"),
            "name": row.get("name"),
            "fetch_problem_date": row.get("fetch_problem_date"),
            "careers_url": row.get("careers_url"),
            "ats_type": row.get("ats_type"),
        }
        for row in stats["problem_rows"]
    ]
    return {
        "has_data": True,
        "countries": countries,
        "totals": totals,
        "by_ats": by_ats,
        "fetch_problem_companies": fetch_problem_companies,
        "country_meta": _overview_country_meta(
            stats["meta_rows"],
            stats["latest_job_by_country"],
            countries,
        ),
    }
