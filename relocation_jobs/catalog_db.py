"""Postgres catalog for companies and matching jobs.

Compatibility shim — import from ``relocation_jobs.catalog`` for new code.
See SCHEMAS.md for the schema architecture.
"""

from relocation_jobs.catalog import *  # noqa: F403
from relocation_jobs.catalog import __all__ as _catalog_all

__all__ = list(_catalog_all) + ["_load_country_from_db"]

# Tests monkeypatch this private helper.
from relocation_jobs.catalog.reads import load_country_from_db as _load_country_from_db
