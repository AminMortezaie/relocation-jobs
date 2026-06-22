"""Path resolution helpers in relocation_jobs.paths."""

from __future__ import annotations

import pytest

from relocation_jobs.core.paths import (
    COUNTRY_FILE_NAMES,
    PROJECT_ROOT,
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


def test_country_file_names_contains_known_countries():
    assert set(COUNTRY_FILE_NAMES) >= {"uk", "germany", "netherlands", "portugal"}
