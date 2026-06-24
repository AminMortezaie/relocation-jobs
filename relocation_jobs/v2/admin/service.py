from __future__ import annotations

import os

from relocation_jobs.core.ats_constants import (
    DEFAULT_CONCURRENCY,
    EXCLUDE_KEYWORDS,
    INCLUDE_KEYWORDS,
    KNOWN_ATS,
)
from relocation_jobs.core.location_tags import COUNTRY_LABELS, SUGGESTED_CITIES, load_custom_cities
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, SUPPORTED_COUNTRIES, data_dir
from relocation_jobs.db import admin_tracking_totals, list_users_with_stats, user_count
from relocation_jobs.v2.catalog.stats import get_catalog_overview
from relocation_jobs.v2.fetch import repo as fetch_repo


def get_system_config(*, scrape_enabled: bool, httpx_available: bool) -> dict:
    custom = load_custom_cities()
    archives = [COUNTRY_ARCHIVE_FILENAMES[key] for key in sorted(SUPPORTED_COUNTRIES)]
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
