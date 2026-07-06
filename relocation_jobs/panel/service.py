from __future__ import annotations

from relocation_jobs.catalog.repo import (
    count_catalog_companies,
    count_fetch_problems,
    load_catalog_companies_page,
    load_country_catalog,
    load_country_meta,
)
from relocation_jobs.core.location_tags import country_label, sync_company_location_fields
from relocation_jobs.core.paths import country_archive_filename, supported_countries
from relocation_jobs.users.repo import (
    load_company_tracking,
    load_job_status_history,
    load_job_tracking,
)
from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.panel.flatten import PanelContext, flatten_company
from relocation_jobs.panel.types import FlattenFilters
from relocation_jobs.shared.timestamps import normalize_ts_for_sort


def _board_activity_sort_key(row: dict) -> str:
    ts = row.get("newest_job_fetched") or row.get("latest_fetched") or ""
    return normalize_ts_for_sort(str(ts).strip())


def _sort_board_page_rows(rows: list[dict]) -> None:
    rows.sort(key=_board_activity_sort_key, reverse=True)


def _board_name_sort_key(row: dict) -> tuple[str, str]:
    return (
        (row.get("country_label") or row.get("country") or "").casefold(),
        (row.get("name") or "").casefold(),
    )


def _normalize_board_sort(sort: str | None) -> str:
    key = (sort or "newest").strip().lower()
    return key if key in ("newest", "name") else "newest"


def load_context(user_id: int | None, country_key: str | None = None) -> PanelContext:
    if not user_id:
        return PanelContext(user_id=None)
    scope_country = country_key if country_key and country_key != "all" else None
    return PanelContext(
        user_id=user_id,
        job_tracking=load_job_tracking(user_id, country=scope_country),
        company_tracking=load_company_tracking(user_id, country=scope_country),
        status_history=load_job_status_history(user_id, country=scope_country),
        mcp_applications=mcp_repo.load_application_summaries(
            user_id,
            country=scope_country,
        ),
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
    filename = country_archive_filename(country_key)
    if not filename:
        return None
    if not data.get("companies") and not data.get("source"):
        return None
    label = country_label(country_key)
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


def _load_country_meta_row(country_key: str, *, cache: dict[str, dict] | None = None) -> dict:
    if cache is not None and country_key in cache:
        return cache[country_key]
    data = load_country_meta(country_key)
    result = data if data is not None else {
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


def _collect_file_meta(country_keys: list[str]) -> list[dict]:
    rows: list[dict] = []
    meta_cache: dict[str, dict] = {}
    for key in country_keys:
        data = _load_country_meta_row(key, cache=meta_cache)
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


def flatten_companies_page(
    filters: FlattenFilters,
    *,
    visible_offset: int,
    limit: int,
    search: str | None = None,
    count_total: bool = False,
    sort: str | None = "newest",
) -> tuple[list[dict], list[dict], int, int | None, bool]:
    sort_key = _normalize_board_sort(sort)
    if sort_key == "newest":
        return _flatten_companies_page_by_activity(
            filters,
            visible_offset=visible_offset,
            limit=limit,
            search=search,
        )
    return _flatten_companies_page_streaming(
        filters,
        visible_offset=visible_offset,
        limit=limit,
        search=search,
        count_total=count_total,
    )


def _flatten_companies_page_streaming(
    filters: FlattenFilters,
    *,
    visible_offset: int,
    limit: int,
    search: str | None,
    count_total: bool,
) -> tuple[list[dict], list[dict], int, int | None, bool]:
    ctx = load_context(filters.user_id, filters.country_key)
    country_keys = _country_keys_for_filters(filters)
    file_meta = _collect_file_meta(country_keys)
    search_key = (search or "").strip().lower() or None
    total_catalog = count_catalog_companies(
        country_keys,
        ats_type=filters.ats_type,
        search=search_key,
    )
    fetch_problem_count = count_fetch_problems(country_keys)
    companies_out: list[dict] = []
    visible_index = 0
    catalog_offset = 0
    batch_size = max(limit, 25)
    start = max(visible_offset, 0)
    has_more = False
    scanning_for_more = False

    while catalog_offset < total_catalog:
        if has_more:
            break
        batch = load_catalog_companies_page(
            country_keys,
            offset=catalog_offset,
            limit=batch_size,
            ats_type=filters.ats_type,
            search=search_key,
        )
        if not batch:
            break
        for country_key, company in batch:
            if has_more:
                break
            label = country_label(country_key)
            row = flatten_company(
                company,
                country_key=country_key,
                country_label=label,
                filters=filters,
                ctx=ctx,
            )
            if not row:
                continue
            if scanning_for_more:
                has_more = True
                break
            if visible_index >= start and len(companies_out) < limit:
                companies_out.append(row)
            visible_index += 1
            if len(companies_out) >= limit and not count_total:
                scanning_for_more = True
        catalog_offset += len(batch)

    total_visible = visible_index if count_total else None
    if len(companies_out) < limit:
        has_more = False
    elif count_total:
        has_more = start + len(companies_out) < visible_index

    return companies_out, file_meta, fetch_problem_count, total_visible, has_more


def _flatten_companies_page_by_activity(
    filters: FlattenFilters,
    *,
    visible_offset: int,
    limit: int,
    search: str | None,
) -> tuple[list[dict], list[dict], int, int | None, bool]:
    ctx = load_context(filters.user_id, filters.country_key)
    country_keys = _country_keys_for_filters(filters)
    file_meta = _collect_file_meta(country_keys)
    search_key = (search or "").strip().lower() or None
    total_catalog = count_catalog_companies(
        country_keys,
        ats_type=filters.ats_type,
        search=search_key,
    )
    fetch_problem_count = count_fetch_problems(country_keys)
    visible_rows: list[dict] = []
    catalog_offset = 0
    batch_size = 50

    while catalog_offset < total_catalog:
        batch = load_catalog_companies_page(
            country_keys,
            offset=catalog_offset,
            limit=batch_size,
            ats_type=filters.ats_type,
            search=search_key,
        )
        if not batch:
            break
        for country_key, company in batch:
            label = country_label(country_key)
            row = flatten_company(
                company,
                country_key=country_key,
                country_label=label,
                filters=filters,
                ctx=ctx,
            )
            if row:
                visible_rows.append(row)
        catalog_offset += len(batch)

    _sort_board_page_rows(visible_rows)
    start = max(visible_offset, 0)
    companies_out = visible_rows[start:start + limit]
    total_visible = len(visible_rows)
    has_more = start + len(companies_out) < total_visible
    return companies_out, file_meta, fetch_problem_count, total_visible, has_more


def _country_keys_for_filters(filters: FlattenFilters) -> list[str]:
    if filters.country_key and filters.country_key != "all":
        return [filters.country_key]
    return sorted(supported_countries())


def flatten_with_filters(filters: FlattenFilters) -> tuple[list[dict], list[dict], int]:
    ctx = load_context(filters.user_id, filters.country_key)
    country_cache: dict[str, dict] = {}
    country_keys = _country_keys_for_filters(filters)
    file_meta = _collect_file_meta(country_keys)
    companies_out: list[dict] = []
    fetch_problem_count = 0

    for key in country_keys:
        data = load_country(key, cache=country_cache)
        if not data.get("companies") and not data.get("source"):
            continue
        label = country_label(key)

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
