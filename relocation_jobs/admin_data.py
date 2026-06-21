"""Aggregated read-only data for the admin dashboard."""

from __future__ import annotations

import os

from relocation_jobs.catalog_db import COUNTRY_LABELS, catalog_has_data
from relocation_jobs.db import admin_tracking_totals, db_read, get_connection, user_count
from relocation_jobs.db_backend import use_postgres
from relocation_jobs.location_tags import SUGGESTED_CITIES, load_custom_cities
from relocation_jobs.paths import COMPANIES_DIR, data_dir


def _row_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _table_has_column(conn, table: str, column: str) -> bool:
    """Return whether ``table.column`` exists (SQLite or Postgres)."""
    if use_postgres():
        try:
            conn.execute(f"SELECT {column} FROM {table} LIMIT 0")
            return True
        except Exception:
            return False

    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return False
    for row in rows:
        if isinstance(row, dict):
            name = row.get("name")
        else:
            try:
                name = row[1]
            except (IndexError, KeyError, TypeError):
                name = None
        if name == column:
            return True
    return False


def _companies_have_column(conn, column: str) -> bool:
    return _table_has_column(conn, "companies", column)


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


def _country_latest_job_fetches(conn) -> dict[str, str]:
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


def _visible_job_counts_by_country(
    stored_by_country: dict[str, dict[str, int]] | None = None,
) -> dict[str, dict[str, int]]:
    """Panel-visible job counts (location gate, catalog not-for-me), no user overlay."""
    from relocation_jobs.panel_data import COUNTRY_FILES, flatten_companies

    stored_by_country = stored_by_country or {}
    out: dict[str, dict[str, int]] = {}
    for key in COUNTRY_FILES:
        stored = stored_by_country.get(
            key,
            {"stored_jobs": 0, "stored_visa_jobs": 0},
        )
        try:
            companies, _, _ = flatten_companies(key, user_id=None)
            jobs = sum(c.get("job_count", len(c.get("jobs", []))) for c in companies)
            visa_jobs = sum(
                1
                for c in companies
                for j in c.get("jobs", [])
                if j.get("visa_sponsorship") is True
            )
            out[key] = {"jobs": jobs, "visa_jobs": visa_jobs}
        except Exception:
            out[key] = {
                "jobs": int(stored.get("stored_jobs") or 0),
                "visa_jobs": int(stored.get("stored_visa_jobs") or 0),
            }
    return out


def get_catalog_overview() -> dict:
    from relocation_jobs.catalog_db import init_catalog_schema

    init_catalog_schema()
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

    with db_read() as conn:
        has_locations_json = _companies_have_column(conn, "locations_json")
        missing_locations_expr = (
            """
                SUM(
                    CASE
                        WHEN locations_json IS NULL OR locations_json IN ('', '[]')
                        THEN 1 ELSE 0
                    END
                ) AS missing_locations
            """
            if has_locations_json
            else "0 AS missing_locations"
        )
        company_rows = conn.execute(
            f"""
            SELECT
                country,
                COUNT(*) AS companies,
                SUM(CASE WHEN fetch_problem = 1 THEN 1 ELSE 0 END) AS fetch_problems,
                SUM(CASE WHEN fetch_ok = 1 THEN 1 ELSE 0 END) AS fetch_ok,
                {missing_locations_expr}
            FROM companies
            GROUP BY country
            ORDER BY country
            """
        ).fetchall()

        job_rows = conn.execute(
            """
            SELECT c.country, COUNT(j.id) AS jobs,
                   SUM(CASE WHEN j.visa_sponsorship = 1 THEN 1 ELSE 0 END) AS visa_jobs
            FROM companies c
            LEFT JOIN matching_jobs j ON j.company_id = c.id
            GROUP BY c.country
            """
        ).fetchall()

        empty_row = conn.execute(
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

        ats_rows = conn.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(ats_type), ''), '(unset)') AS ats_type,
                COUNT(*) AS companies
            FROM companies
            GROUP BY COALESCE(NULLIF(TRIM(ats_type), ''), '(unset)')
            ORDER BY companies DESC, ats_type ASC
            """
        ).fetchall()

        problem_rows = conn.execute(
            """
            SELECT country, name, fetch_problem_date, careers_url, ats_type
            FROM companies
            WHERE fetch_problem = 1
            ORDER BY fetch_problem_date DESC, name ASC
            LIMIT 100
            """
        ).fetchall()

        meta_rows = conn.execute(
            """
            SELECT country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs
            FROM country_meta
            ORDER BY country
            """
        ).fetchall()

        latest_job_by_country = _country_latest_job_fetches(conn)

    jobs_by_country = {
        _row_dict(row)["country"]: {
            "stored_jobs": int(_row_dict(row).get("jobs") or 0),
            "stored_visa_jobs": int(_row_dict(row).get("visa_jobs") or 0),
        }
        for row in job_rows
    }
    visible_by_country = _visible_job_counts_by_country(jobs_by_country)

    empty_companies = int(_row_dict(empty_row).get("n") or 0)

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
    countries: list[dict] = []
    for row in company_rows:
        data = _row_dict(row)
        country = data["country"]
        companies = int(data.get("companies") or 0)
        fetch_problems = int(data.get("fetch_problems") or 0)
        fetch_ok = int(data.get("fetch_ok") or 0)
        missing_locations = int(data.get("missing_locations") or 0)
        stored_info = jobs_by_country.get(
            country,
            {"stored_jobs": 0, "stored_visa_jobs": 0},
        )
        visible_info = visible_by_country.get(country, {"jobs": 0, "visa_jobs": 0})
        countries.append(
            {
                "country": country,
                "label": COUNTRY_LABELS.get(country, country.title()),
                "companies": companies,
                "jobs": visible_info["jobs"],
                "stored_jobs": stored_info["stored_jobs"],
                "visa_jobs": visible_info["visa_jobs"],
                "stored_visa_jobs": stored_info["stored_visa_jobs"],
                "fetch_problems": fetch_problems,
                "fetch_ok": fetch_ok,
                "missing_locations": missing_locations,
            }
        )
        totals["companies"] += companies
        totals["jobs"] += visible_info["jobs"]
        totals["stored_jobs"] += stored_info["stored_jobs"]
        totals["visa_jobs"] += visible_info["visa_jobs"]
        totals["stored_visa_jobs"] += stored_info["stored_visa_jobs"]
        totals["fetch_problems"] += fetch_problems
        totals["fetch_ok"] += fetch_ok
        totals["missing_locations"] += missing_locations

    by_ats = [
        {
            "ats_type": _row_dict(row).get("ats_type"),
            "companies": int(_row_dict(row).get("companies") or 0),
        }
        for row in ats_rows
    ]

    fetch_problem_companies = [
        {
            "country": _row_dict(row).get("country"),
            "name": _row_dict(row).get("name"),
            "fetch_problem_date": _row_dict(row).get("fetch_problem_date"),
            "careers_url": _row_dict(row).get("careers_url"),
            "ats_type": _row_dict(row).get("ats_type"),
        }
        for row in problem_rows
    ]

    companies_by_country = {c["country"]: c["companies"] for c in countries}
    meta_by_country: dict[str, dict] = {}
    for row in meta_rows:
        data = _row_dict(row)
        country = data.get("country", "")
        last_fetch = _max_timestamp(
            data.get("jobs_fetched"),
            latest_job_by_country.get(country),
        )
        meta_by_country[country] = {
            "country": country,
            "label": COUNTRY_LABELS.get(
                country,
                (country or "").title(),
            ),
            "source": data.get("source"),
            "catalog_imported": data.get("fetched"),
            "last_fetch": last_fetch,
            "updated": data.get("updated"),
            "jobs_fetched": data.get("jobs_fetched"),
            "total": companies_by_country.get(country, int(data.get("total") or 0)),
            "last_fetch_new_jobs": int(data.get("last_fetch_new_jobs") or 0),
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

    country_meta = sorted(meta_by_country.values(), key=lambda row: row["country"])

    return {
        "has_data": True,
        "countries": countries,
        "totals": totals,
        "by_ats": by_ats,
        "fetch_problem_companies": fetch_problem_companies,
        "country_meta": country_meta,
    }


def get_system_config(*, scrape_enabled: bool, httpx_available: bool) -> dict:
    from relocation_jobs.scrape_jobs import (
        DEFAULT_CONCURRENCY,
        EXCLUDE_KEYWORDS,
        INCLUDE_KEYWORDS,
        KNOWN_ATS,
    )

    custom = load_custom_cities()
    archives = sorted(p.name for p in COMPANIES_DIR.glob("*_companies.json"))
    return {
        "database": "postgres" if use_postgres() else "sqlite",
        "data_dir": str(data_dir()),
        "scrape_enabled": scrape_enabled,
        "allow_register": os.environ.get("PANEL_ALLOW_REGISTER", "").lower()
        in ("1", "true", "yes"),
        "httpx_available": httpx_available,
        "default_concurrency": DEFAULT_CONCURRENCY,
        "max_concurrency": 64,
        "include_keywords": INCLUDE_KEYWORDS,
        "exclude_keywords": EXCLUDE_KEYWORDS,
        "known_ats_count": len(KNOWN_ATS),
        "known_ats_companies": sorted(KNOWN_ATS.keys()),
        "suggested_cities": {
            key: len(values) for key, values in SUGGESTED_CITIES.items()
        },
        "custom_cities": custom,
        "countries": [
            {"id": key, "label": label} for key, label in COUNTRY_LABELS.items()
        ],
        "archives": archives,
    }


def get_admin_overview(*, fetch_state: dict | None = None) -> dict:
    catalog = get_catalog_overview()
    tracking = admin_tracking_totals()
    return {
        "users": user_count(),
        "catalog": catalog["totals"],
        "tracking": tracking,
        "fetch": fetch_state or {"running": False},
    }
