from __future__ import annotations

from relocation_jobs.core.ats_constants import ATS_TYPE_CHOICES
from relocation_jobs.core.location_tags import all_country_labels
from relocation_jobs.shared.board_contract import (
    AGGREGATOR_ATS_TYPES,
    CATALOG_KIND_REMOTE,
    SOURCED_ATS_TYPE,
    countries_for_kind,
)


def list_remote_countries() -> list[dict[str, str]]:
    return countries_for_kind(CATALOG_KIND_REMOTE, all_country_labels())


def list_remote_ats_types() -> list[dict[str, str]]:
    allowed = AGGREGATOR_ATS_TYPES | {SOURCED_ATS_TYPE}
    return [
        {"id": key, "label": label}
        for key, label in ATS_TYPE_CHOICES
        if key in allowed
    ] + [{"id": SOURCED_ATS_TYPE, "label": "Sourced employer"}]
