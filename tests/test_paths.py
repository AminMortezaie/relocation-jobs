"""Path resolution helpers in relocation_jobs.paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from relocation_jobs.paths import (
    COUNTRY_FILE_NAMES,
    COMPANIES_DIR,
    PROJECT_ROOT,
    archive_json_path,
    archive_json_path_for_filename,
    bundled_country_json,
    country_json_path,
    country_json_path_for_filename,
    data_dir,
    ensure_data_dir,
    resolve_json_path,
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


def test_archive_paths():
    assert archive_json_path("uk") == COMPANIES_DIR / "uk_companies.json"
    assert archive_json_path_for_filename("uk_companies.json") == COMPANIES_DIR / "uk_companies.json"
    assert country_json_path("uk") == archive_json_path("uk")
    assert country_json_path_for_filename("uk_companies.json") == archive_json_path_for_filename(
        "uk_companies.json"
    )
    assert bundled_country_json("uk_companies.json") == COMPANIES_DIR / "uk_companies.json"
    assert set(COUNTRY_FILE_NAMES) >= {"uk", "germany", "netherlands", "portugal"}


def test_resolve_json_path_existing_file(tmp_path, monkeypatch):
    f = tmp_path / "custom.json"
    f.write_text("{}", encoding="utf-8")
    assert resolve_json_path(f) == f.resolve()


def test_resolve_json_path_by_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    name = "find_me.json"
    (tmp_path / name).write_text("{}", encoding="utf-8")
    assert resolve_json_path(name) == (tmp_path / name).resolve()


def test_resolve_json_path_companies_dir(tmp_path, monkeypatch):
    name = "uk_companies.json"
    if (COMPANIES_DIR / name).is_file():
        resolved = resolve_json_path(name)
        assert resolved.is_file()
    else:
        resolved = resolve_json_path("nonexistent_xyz.json")
        assert resolved == (COMPANIES_DIR / "nonexistent_xyz.json").resolve()


def test_resolve_json_path_missing_returns_companies_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resolved = resolve_json_path("does_not_exist_anywhere.json")
    assert resolved == (COMPANIES_DIR / "does_not_exist_anywhere.json").resolve()


def test_resolve_json_path_data_dir(tmp_data_dir, monkeypatch):
    name = "data_only.json"
    path = tmp_data_dir / name
    path.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert resolve_json_path(name) == path.resolve()
