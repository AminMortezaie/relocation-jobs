from __future__ import annotations

import os
from datetime import datetime

from relocation_jobs.users.applied import _timezone, local_day_utc_bounds

from relocation_jobs.core.ats_constants import (
    DEFAULT_CONCURRENCY,
    EXCLUDE_KEYWORDS,
    INCLUDE_KEYWORDS,
    KNOWN_ATS,
    MAX_CONCURRENCY,
)
from relocation_jobs.core.location_tags import SUGGESTED_CITIES, all_country_labels, load_custom_cities, load_custom_countries
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, country_archive_filename, data_dir, supported_countries
from relocation_jobs.users.repo import list_users_with_stats, user_count
from relocation_jobs.catalog.custom_countries import countries_use_redis
from relocation_jobs.catalog.repo import get_catalog_overview
from relocation_jobs.core.redis_client import ping_redis, redis_enabled
from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.fetch.scheduler import (
    schedule_concurrency,
    schedule_enabled,
    schedule_interval_hours,
)
from relocation_jobs.panel.service import flatten_companies_for_stats
from relocation_jobs.panel.stats import compute_stats
from relocation_jobs.core.db import db_read


def get_system_config(*, scrape_enabled: bool, httpx_available: bool) -> dict:
    custom = load_custom_cities()
    archives = [country_archive_filename(key) for key in sorted(supported_countries())]
    return {
        "database": "postgres",
        "redis": "connected" if countries_use_redis() else ("configured" if redis_enabled() else "off"),
        "redis_ping": ping_redis() if redis_enabled() else False,
        "countries_store": "redis" if countries_use_redis() else "postgres",
        "data_dir": str(data_dir()),
        "scrape_enabled": scrape_enabled,
        "allow_register": os.environ.get("PANEL_ALLOW_REGISTER", "").lower()
        in ("1", "true", "yes"),
        "httpx_available": httpx_available,
        "default_concurrency": DEFAULT_CONCURRENCY,
        "max_concurrency": MAX_CONCURRENCY,
        "include_keywords": INCLUDE_KEYWORDS,
        "exclude_keywords": EXCLUDE_KEYWORDS,
        "known_ats_count": len(KNOWN_ATS),
        "known_ats_companies": sorted(KNOWN_ATS.keys()),
        "suggested_cities": {key: len(values) for key, values in SUGGESTED_CITIES.items()},
        "custom_cities": custom,
        "custom_countries": load_custom_countries(),
        "countries": [
            {"id": key, "label": label} for key, label in sorted(all_country_labels().items())
        ],
        "archives": archives,
    }


def get_worker_status(*, fetch_state: dict | None, scrape_enabled: bool) -> dict:
    return {
        "fetch": fetch_state or {"running": False},
        "last_country_run": fetch_repo.latest_finished_country_run(),
        "panel_scrape_enabled": scrape_enabled,
        "schedule_enabled": schedule_enabled(),
        "schedule_interval_hours": schedule_interval_hours(),
        "schedule_concurrency": schedule_concurrency(),
        "schedule_countries": (os.environ.get("FETCH_SCHEDULE_COUNTRIES") or "").strip(),
    }


def compute_admin_panel_stats(
    *,
    user_id: int,
    country_key: str | None = None,
    location: str | None = None,
    ats_type: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    companies, file_meta, fetch_problem_count = flatten_companies_for_stats(
        country_key,
        location=location,
        ats_type=ats_type,
        user_id=user_id,
    )
    return compute_stats(
        companies,
        file_meta,
        fetch_problem_count=fetch_problem_count,
        user_id=user_id,
        country_key=country_key,
        timezone_name=timezone_name,
    )


def get_admin_overview(*, fetch_state: dict | None = None) -> dict:
    catalog = get_catalog_overview()
    return {
        "users": user_count(),
        "catalog": catalog["totals"],
        "fetch": fetch_state or {"running": False},
    }


def get_recently_fetched_jobs(
    *,
    limit: int = 30,
    timezone_name: str | None = None,
) -> list[dict]:
    start_utc, end_utc = local_day_utc_bounds(timezone_name)
    tz = _timezone(timezone_name)
    start_date = datetime.fromisoformat(start_utc).astimezone(tz).date().isoformat()
    end_date = datetime.fromisoformat(end_utc).astimezone(tz).date().isoformat()
    with db_read() as conn:
        rows = conn.execute(
            """
            SELECT j.title, j.url, j.fetched, j.visa_sponsorship,
                   c.name AS company_name, c.country
            FROM matching_jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.fetched >= %s AND j.fetched < %s
            ORDER BY j.fetched DESC
            LIMIT %s
            """,
            (start_date, end_date, max(1, min(limit, 200))),
        ).fetchall()
    return [dict(r) for r in rows]


def get_admin_dashboard(
    *,
    fetch_state: dict | None = None,
    scrape_enabled: bool,
    httpx_available: bool,
    fetch_runs_limit: int = 15,
) -> dict:
    catalog = get_catalog_overview()
    return {
        "user_count": user_count(),
        "worker": get_worker_status(
            fetch_state=fetch_state,
            scrape_enabled=scrape_enabled,
        ),
        "panel_stats": None,
        "catalog": catalog,
        "users": {"users": list_users_with_stats()},
        "runs": {"runs": fetch_repo.list_all_fetch_runs(limit=fetch_runs_limit)},
        "config": get_system_config(
            scrape_enabled=scrape_enabled,
            httpx_available=httpx_available,
        ),
    }
