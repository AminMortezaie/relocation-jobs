"""Database backend selection: local SQLite or hosted Postgres (Neon free tier)."""

from __future__ import annotations

import os


def use_postgres() -> bool:
    return bool(os.environ.get("DATABASE_URL", "").strip())


def placeholder() -> str:
    return "%s" if use_postgres() else "?"
