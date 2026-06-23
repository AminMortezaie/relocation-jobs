"""Catalog read queries."""

from __future__ import annotations

from collections import defaultdict

from relocation_jobs.core.db import db_read
from relocation_jobs.core.job_identity import job_idempotency_key

from relocation_jobs.catalog.cache import _country_cache, _country_cache_lock, invalidate_country_cache
from relocation_jobs.catalog.serialize import (
    company_row_to_dict,
    job_row_to_dict,
    row_dict,
)

def catalog_has_data() -> bool:
    with db_read() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()
    data = row_dict(row)
    return int(data.get("n") or 0) > 0

def load_country_from_db(country_key: str) -> dict | None:
    with db_read() as conn:
        meta_row = conn.execute(
            "SELECT * FROM country_meta WHERE country = %s",
            (country_key,),
        ).fetchone()
        if meta_row is None:
            return None

        meta = row_dict(meta_row)

        companies_rows = conn.execute(
            "SELECT * FROM companies WHERE country = %s ORDER BY name",
            (country_key,),
        ).fetchall()

        company_ids = [row_dict(crow)["id"] for crow in companies_rows]
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
                jdata = row_dict(job_row)
                jobs_by_company[int(jdata["company_id"])].append(job_row_to_dict(job_row))

        companies: list[dict] = []
        for crow in companies_rows:
            cdata = row_dict(crow)
            company_id = int(cdata["id"])
            companies.append(company_row_to_dict(cdata, jobs_by_company[company_id]))

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
    with _country_cache_lock:
        if country_key in _country_cache:
            return _country_cache[country_key]

    data = load_country_from_db(country_key)
    with _country_cache_lock:
        _country_cache[country_key] = data
    return data

