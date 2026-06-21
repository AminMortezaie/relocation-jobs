"""Project paths: SQLite data dir, git-tracked JSON archives, static assets."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
COMPANIES_DIR = PROJECT_ROOT / "companies"
STATIC_DIR = PACKAGE_DIR / "static"

COUNTRY_FILE_NAMES: dict[str, str] = {
    "germany": "germany_companies.json",
    "netherlands": "netherlands_companies.json",
    "uk": "uk_companies.json",
    "portugal": "portugal_companies.json",
}

COUNTRY_JSON_FILENAMES = list(COUNTRY_FILE_NAMES.values())


def data_dir() -> Path:
    raw = os.environ.get("PANEL_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return PROJECT_ROOT / "data"


def ensure_data_dir() -> Path:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def archive_json_path(country_key: str) -> Path:
    """Read-only JSON snapshot path in companies/ (git archive)."""
    filename = COUNTRY_FILE_NAMES[country_key]
    return COMPANIES_DIR / filename


def archive_json_path_for_filename(filename: str) -> Path:
    """Read-only JSON snapshot path in companies/ (git archive)."""
    return COMPANIES_DIR / filename


def country_json_path(country_key: str) -> Path:
    """Legacy alias — archive JSON path, not the live data store."""
    return archive_json_path(country_key)


def country_json_path_for_filename(filename: str) -> Path:
    """Legacy alias — archive JSON path, not the live data store."""
    return archive_json_path_for_filename(filename)


def bundled_country_json(filename: str) -> Path:
    return COMPANIES_DIR / filename


def resolve_json_path(path: str | Path) -> Path:
    """Resolve CLI --file args: cwd, companies/ archive, or legacy data/ JSON."""
    p = Path(path)
    if p.is_file():
        return p.resolve()
    name = p.name
    for candidate in (Path.cwd() / name, COMPANIES_DIR / name, data_dir() / name):
        if candidate.is_file():
            return candidate.resolve()
    return (COMPANIES_DIR / name).resolve()
