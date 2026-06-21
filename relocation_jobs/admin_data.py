"""Backward-compatibility shim — logic lives in services/admin_service.py."""

from relocation_jobs.services.admin_service import (  # noqa: F401
    get_admin_overview,
    get_catalog_overview,
    get_system_config,
)
