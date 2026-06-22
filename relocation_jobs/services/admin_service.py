"""Admin dashboard aggregation service.

Composes the catalog repository (catalog_db), the tracking repository (db),
and the catalog query layer — no raw SQL here.
"""

from __future__ import annotations

import os

from relocation_jobs.catalog_db import (
    catalog_has_data,
    load_catalog_stats,
)
from relocation_jobs.db import admin_tracking_totals, user_count
from relocation_jobs.core.location_tags import COUNTRY_LABELS, SUGGESTED_CITIES, load_custom_cities
from relocation_jobs.core.paths import COMPANIES_DIR, data_dir


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


def _visible_job_counts_by_country(
    stored_by_country: dict[str, dict[str, int]] | None = None,
) -> dict[str, dict[str, int]]:
    from relocation_jobs.services.catalog_service import COUNTRY_FILES, flatten_companies

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
    visible_by_country = _visible_job_counts_by_country(jobs_by_country)

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
        country = row["country"]
        companies = int(row.get("companies") or 0)
        fetch_problems = int(row.get("fetch_problems") or 0)
        fetch_ok = int(row.get("fetch_ok") or 0)
        missing_locations = int(row.get("missing_locations") or 0)
        stored_info = jobs_by_country.get(country, {"stored_jobs": 0, "stored_visa_jobs": 0})
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
        {"ats_type": row.get("ats_type"), "companies": int(row.get("companies") or 0)}
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
            "label": COUNTRY_LABELS.get(country, (country or "").title()),
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
        "database": "postgres",
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
        "suggested_cities": {key: len(values) for key, values in SUGGESTED_CITIES.items()},
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
