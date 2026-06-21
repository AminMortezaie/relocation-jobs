"""Migration script entry checks."""

from __future__ import annotations

import pytest


def test_migrate_requires_database_url(tmp_path, monkeypatch):
    import scripts.migrate_sqlite_to_neon as mig

    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = tmp_path / "panel.db"
    db.write_bytes(b"")  # exists but empty — fails later if URL were set

    with pytest.raises(SystemExit, match="DATABASE_URL"):
        mig.migrate(sqlite_path=db, force=False)


def test_migrate_requires_sqlite_file(monkeypatch):
    import scripts.migrate_sqlite_to_neon as mig

    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    missing = mig.PROJECT_ROOT / "data" / "no-such-panel.db"

    with pytest.raises(SystemExit, match="SQLite database not found"):
        mig.migrate(sqlite_path=missing, force=False)
