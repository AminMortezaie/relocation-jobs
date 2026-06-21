"""Database backend selection helpers."""

import pytest

from relocation_jobs.db_backend import placeholder, use_postgres


def test_use_postgres_false_by_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert use_postgres() is False
    assert placeholder() == "?"


def test_use_postgres_true_with_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    assert use_postgres() is True
    assert placeholder() == "%s"
