"""Catalog aggregation queries for admin dashboards."""

from __future__ import annotations

from relocation_jobs.core.db import db_read

from relocation_jobs.catalog.util import row_dict

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
    return [row_dict(r) for r in rows]


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
    return [row_dict(r) for r in rows]


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
    return int((row_dict(row) or {}).get("n") or 0)


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
    return [row_dict(r) for r in rows]


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
    return [row_dict(r) for r in rows]


def query_country_meta(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs
        FROM country_meta
        ORDER BY country
        """
    ).fetchall()
    return [row_dict(r) for r in rows]


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
        r = row_dict(row)
        country = r.get("country")
        latest = (r.get("latest_job_fetch") or "").strip()
        if country and latest:
            out[country] = latest
    return out
