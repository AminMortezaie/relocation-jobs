from __future__ import annotations

import json
from typing import Any

from relocation_jobs.shared.schema import BaseSchema

CATALOG_KIND_RELOCATION = "relocation"
CATALOG_KIND_REMOTE = "remote"
CATALOG_KINDS = frozenset({CATALOG_KIND_RELOCATION, CATALOG_KIND_REMOTE})

REMOTE_COUNTRY_KEYS = frozenset({"remote-ok", "remote-dxb", "remote-joblet"})
AGGREGATOR_ATS_TYPES = frozenset({"remoteok", "remotedxb", "joblet"})
AGGREGATOR_SOURCE_KEYS = frozenset({"remoteok", "remotedxb", "joblet", "aggregator"})
SOURCED_ATS_TYPE = "sourced"


class BoardMeta(BaseSchema):
    country: str = "all"
    ats_type: str | None = None
    location: str | None = None
    fetch_problem_total: int = 0
    latest_fetch_new_jobs: int = 0
    page: int = 1
    page_size: int = 25
    total_companies: int | None = None
    total_pages: int | None = None
    has_more: bool = False
    sort: str = "newest"


def is_remote_country_key(country_key: str | None) -> bool:
    return (country_key or "").strip().lower() in REMOTE_COUNTRY_KEYS


def normalize_catalog_kind(value: str | None) -> str:
    kind = (value or "").strip().lower()
    return kind if kind in CATALOG_KINDS else CATALOG_KIND_RELOCATION


def catalog_kind_for_write(
    *,
    country_key: str | None,
    ats_type: str | None = None,
    sources: list[str] | None = None,
) -> str:
    if is_remote_country_key(country_key):
        return CATALOG_KIND_REMOTE
    ats = (ats_type or "").strip().lower()
    if ats in AGGREGATOR_ATS_TYPES or ats == SOURCED_ATS_TYPE:
        return CATALOG_KIND_REMOTE
    source_set = {(s or "").strip().lower() for s in (sources or []) if s}
    if source_set & AGGREGATOR_SOURCE_KEYS:
        return CATALOG_KIND_REMOTE
    return CATALOG_KIND_RELOCATION


def infer_catalog_kind_from_row(
    *,
    country: str | None,
    ats_type: str | None,
    sources_json: Any = None,
) -> str:
    sources: list[str] = []
    if isinstance(sources_json, list):
        sources = [str(s) for s in sources_json]
    elif isinstance(sources_json, str) and sources_json.strip():
        raw = sources_json.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = []
            if isinstance(parsed, list):
                sources = [str(s) for s in parsed]
    return catalog_kind_for_write(
        country_key=country,
        ats_type=ats_type,
        sources=sources,
    )


def board_page_payload(
    *,
    companies: list[dict],
    meta: dict,
    user_stats: dict,
) -> dict:
    return {
        "companies": companies,
        "meta": meta,
        "user_stats": user_stats,
    }


def countries_for_kind(kind: str, all_labels: dict[str, str]) -> list[dict[str, str]]:
    normalized = normalize_catalog_kind(kind)
    items = sorted(all_labels.items())
    if normalized == CATALOG_KIND_REMOTE:
        filtered = [(k, label) for k, label in items if is_remote_country_key(k)]
        all_label = "All remote boards"
    else:
        filtered = [(k, label) for k, label in items if not is_remote_country_key(k)]
        all_label = "All countries"
    return [
        {"id": "all", "label": all_label},
        *[{"id": key, "label": label} for key, label in filtered],
    ]
