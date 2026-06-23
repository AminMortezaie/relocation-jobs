"""Path resolution helpers in relocation_jobs.paths."""

from __future__ import annotations

import pytest

from relocation_jobs.core.paths import (
    COUNTRY_ARCHIVE_FILENAMES,
    PROJECT_ROOT,
    SUPPORTED_COUNTRIES,
    data_dir,
    ensure_data_dir,
)


def test_data_dir_default():
    assert data_dir() == PROJECT_ROOT / "data"


def test_data_dir_from_env(tmp_data_dir, monkeypatch):
    monkeypatch.setenv("PANEL_DATA_DIR", str(tmp_data_dir))
    assert data_dir() == tmp_data_dir


def test_ensure_data_dir(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "data"
    monkeypatch.setenv("PANEL_DATA_DIR", str(target))
    created = ensure_data_dir()
    assert created == target
    assert target.is_dir()


def test_supported_countries_contains_known_countries():
    assert SUPPORTED_COUNTRIES >= {"uk", "germany", "netherlands", "portugal"}


def test_country_archive_filenames():
    assert COUNTRY_ARCHIVE_FILENAMES["uk"] == "uk_companies.json"
