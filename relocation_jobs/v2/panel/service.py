from __future__ import annotations

from relocation_jobs.v2.catalog.repo import load_country_catalog
from relocation_jobs.core.location_tags import COUNTRY_LABELS, sync_company_location_fields
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, SUPPORTED_COUNTRIES
from relocation_jobs.v2.users.repo import (
    load_company_tracking,
    load_job_status_history,
    load_job_tracking,
)
from relocation_jobs.v2.panel.flatten import PanelContext, flatten_company
from relocation_jobs.v2.panel.types import FlattenFilters


def load_context(user_id: int | None) -> PanelContext:
    if not user_id:
        return PanelContext(user_id=None)
    return PanelContext(
        user_id=user_id,
        job_tracking=load_job_tracking(user_id),
        company_tracking=load_company_tracking(user_id),
        status_history=load_job_status_history(user_id),
    )


def load_country(country_key: str, *, cache: dict[str, dict] | None = None) -> dict:
    if cache is not None and country_key in cache:
        return cache[country_key]
    data = load_country_catalog(country_key)
    if data is not None:
        for company in data.get("companies") or []:
            sync_company_location_fields(company, catalog_country=country_key)
        result = data
    else:
        result = {
            "source": "",
            "fetched": "",
            "updated": "",
            "jobs_fetched": "",
            "total": 0,
            "companies": [],
        }
    if cache is not None:
        cache[country_key] = result
    return result


def _file_meta_row(country_key: str, data: dict) -> dict | None:
    filename = COUNTRY_ARCHIVE_FILENAMES.get(country_key)
    if not filename:
        return None
    if not data.get("companies") and not data.get("source"):
        return None
    label = COUNTRY_LABELS.get(country_key, country_key)
    return {
        "country": country_key,
        "label": label,
        "file": filename,
        "fetched": data.get("fetched", ""),
        "updated": data.get("updated", data.get("jobs_fetched", "")),
        "jobs_fetched": data.get("jobs_fetched", ""),
        "total_companies": data.get("total", len(data.get("companies", []))),
        "source": data.get("source", ""),
        "last_fetch_new_jobs": int(data.get("last_fetch_new_jobs") or 0),
    }


def _collect_file_meta(country_keys: list[str], cache: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for key in country_keys:
        data = load_country(key, cache=cache)
        row = _file_meta_row(key, data)
        if row:
            rows.append(row)
    return rows


def flatten_companies(
    country_key: str | None = None,
    *,
    visa_only: bool = False,
    hide_applied: bool = False,
    hide_empty: bool = False,
    not_applied_only: bool = False,
    hide_position_applied: bool = False,
    hide_position_rejected: bool = False,
    position_applied_only: bool = False,
    position_rejected_only: bool = False,
    position_looking_to_apply_only: bool = False,
    fetch_ok_only: bool = False,
    fetch_problem_only: bool = False,
    location: str | None = None,
    city: str | None = None,
    ats_type: str | None = None,
    user_id: int | None = None,
) -> tuple[list[dict], list[dict], int]:
    filters = FlattenFilters.from_kwargs(
        country_key=country_key,
        user_id=user_id,
        visa_only=visa_only,
        hide_applied=hide_applied,
        hide_empty=hide_empty,
        not_applied_only=not_applied_only,
        fetch_ok_only=fetch_ok_only,
        fetch_problem_only=fetch_problem_only,
        location=location,
        city=city,
        ats_type=ats_type,
        hide_position_applied=hide_position_applied,
        hide_position_rejected=hide_position_rejected,
        position_applied_only=position_applied_only,
        position_rejected_only=position_rejected_only,
        position_looking_to_apply_only=position_looking_to_apply_only,
    )
    return flatten_with_filters(filters)


def flatten_with_filters(filters: FlattenFilters) -> tuple[list[dict], list[dict], int]:
    ctx = load_context(filters.user_id)
    country_cache: dict[str, dict] = {}
    meta_keys = (
        [filters.country_key]
        if filters.country_key and filters.country_key != "all"
        else sorted(SUPPORTED_COUNTRIES)
    )
    file_meta = _collect_file_meta(meta_keys, country_cache)
    companies_out: list[dict] = []
    fetch_problem_count = 0

    for key in sorted(SUPPORTED_COUNTRIES):
        data = load_country(key, cache=country_cache)
        if not data.get("companies") and not data.get("source"):
            continue
        label = COUNTRY_LABELS.get(key, key)

        for company in data.get("companies", []):
            if company.get("fetch_problem"):
                fetch_problem_count += 1
            row = flatten_company(
                company,
                country_key=key,
                country_label=label,
                filters=filters,
                ctx=ctx,
            )
            if row:
                companies_out.append(row)

    return companies_out, file_meta, fetch_problem_count
