from __future__ import annotations

from relocation_jobs.core.db import db_read
from relocation_jobs.core.location_tags import country_label
from relocation_jobs.core.paths import supported_countries


def _row_dict(row) -> dict:
    return dict(row) if row else {}


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
    return [_row_dict(r) for r in rows]


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
    return [_row_dict(r) for r in rows]


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
    return int((_row_dict(row) or {}).get("n") or 0)


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
    return [_row_dict(r) for r in rows]


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
    return [_row_dict(r) for r in rows]


def _query_country_meta(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs
        FROM country_meta
        ORDER BY country
        """
    ).fetchall()
    return [_row_dict(r) for r in rows]


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
        data = _row_dict(row)
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


def get_catalog_overview() -> dict:
    if not catalog_has_data():
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

    stats = load_catalog_stats()
    company_rows = stats["company_rows"]
    job_rows = stats["job_rows"]
    empty_companies = stats["empty_companies"]
    ats_rows = stats["ats_rows"]
    problem_rows = stats["problem_rows"]
    meta_rows = stats["meta_rows"]
    latest_job_by_country = stats["latest_job_by_country"]

    jobs_by_country = {
        row["country"]: {
            "stored_jobs": int(row.get("jobs") or 0),
            "stored_visa_jobs": int(row.get("visa_jobs") or 0),
        }
        for row in job_rows
    }

    countries = []
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
    by_ats = [
        {"ats_type": row["ats_type"], "companies": int(row.get("companies") or 0)}
        for row in ats_rows
    ]
    fetch_problem_companies = [
        {
            "country": row.get("country"),
            "name": row.get("name"),
            "fetch_problem_date": row.get("fetch_problem_date"),
            "careers_url": row.get("careers_url"),
            "ats_type": row.get("ats_type"),
        }
        for row in problem_rows
    ]

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

    return {
        "has_data": True,
        "countries": countries,
        "totals": totals,
        "by_ats": by_ats,
        "fetch_problem_companies": fetch_problem_companies,
        "country_meta": sorted(meta_by_country.values(), key=lambda row: row["country"]),
    }
