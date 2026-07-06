"""Project paths and country configuration."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE_DIR = PROJECT_ROOT / "relocation_jobs"
COMPANIES_DIR = PROJECT_ROOT / "companies"
STATIC_DIR = PACKAGE_DIR / "static"

# Country keys supported at runtime (Postgres catalog).
SUPPORTED_COUNTRIES: frozenset[str] = frozenset(
    {"germany", "netherlands", "uk", "portugal"}
)


def supported_countries() -> frozenset[str]:
    from relocation_jobs.core.location_tags import supported_country_keys

    return supported_country_keys()

# Legacy git-archive filenames (companies/*.json) — not read at runtime.
COUNTRY_ARCHIVE_FILENAMES: dict[str, str] = {
    "germany": "germany_companies.json",
    "netherlands": "netherlands_companies.json",
    "uk": "uk_companies.json",
    "portugal": "portugal_companies.json",
}


def data_dir() -> Path:
    raw = os.environ.get("PANEL_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return PROJECT_ROOT / "data"


def ensure_data_dir() -> Path:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
