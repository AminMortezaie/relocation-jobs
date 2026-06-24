from __future__ import annotations

import json
from collections import defaultdict

from relocation_jobs.core.db import db_read
from relocation_jobs.core.job_identity import job_idempotency_key


def _row(row) -> dict:
    return dict(row) if row else {}


def _visa(raw) -> bool | None:
    if raw is None:
        return None
    return bool(raw)


def _job_row(row) -> dict:
    data = _row(row)
    job = {
        "title": data.get("title") or "",
        "url": data.get("url") or "",
        "fetched": data.get("fetched") or "",
        "last_seen": data.get("last_seen") or "",
        "idempotency_key": data.get("idempotency_key") or "",
        "visa_sponsorship": _visa(data.get("visa_sponsorship")),
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


def get_job_by_url(job_url: str) -> dict | None:
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
    return _row(row) or None
