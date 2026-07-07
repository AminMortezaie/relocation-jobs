from __future__ import annotations

import os

from relocation_jobs.core.ats_constants import (
    DEFAULT_CONCURRENCY,
    EXCLUDE_KEYWORDS,
    INCLUDE_KEYWORDS,
    KNOWN_ATS,
    MAX_CONCURRENCY,
)
from relocation_jobs.core.location_tags import SUGGESTED_CITIES, all_country_labels, load_custom_cities, load_custom_countries
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, country_archive_filename, data_dir, supported_countries
from relocation_jobs.db import admin_tracking_totals, list_users_with_stats, user_count
from relocation_jobs.catalog.custom_countries import countries_use_redis
from relocation_jobs.catalog.stats import get_catalog_overview
from relocation_jobs.core.redis_client import ping_redis, redis_enabled
from relocation_jobs.fetch import repo as fetch_repo


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


def get_admin_overview(*, fetch_state: dict | None = None) -> dict:
    catalog = get_catalog_overview()
    return {
        "users": user_count(),
        "catalog": catalog["totals"],
        "tracking": admin_tracking_totals(),
        "fetch": fetch_state or {"running": False},
    }


def get_admin_dashboard(
    *,
    fetch_state: dict | None = None,
    scrape_enabled: bool,
    httpx_available: bool,
    fetch_runs_limit: int = 50,
) -> dict:
    catalog = get_catalog_overview()
    return {
        "overview": {
            "users": user_count(),
            "catalog": catalog["totals"],
            "tracking": admin_tracking_totals(),
            "fetch": fetch_state or {"running": False},
        },
        "catalog": catalog,
        "users": {"users": list_users_with_stats()},
        "runs": {"runs": fetch_repo.list_all_fetch_runs(limit=fetch_runs_limit)},
        "config": get_system_config(
            scrape_enabled=scrape_enabled,
            httpx_available=httpx_available,
        ),
    }
