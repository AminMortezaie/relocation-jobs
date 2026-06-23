"""Catalog DB helpers."""

from __future__ import annotations

from datetime import date


def today() -> str:
    return date.today().isoformat()


def row_dict(row) -> dict:
    if row is None:
        return {}
    return row if isinstance(row, dict) else dict(row)


def visa_to_db(value) -> int | None:
    if value is True:
        return 1
    if value is False:
        return 0
    return None


def visa_from_db(value) -> bool | None:
    if value is None:
        return None
    return bool(value)
