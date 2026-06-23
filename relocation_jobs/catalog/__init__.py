"""Postgres catalog repository for companies and matching jobs."""

from relocation_jobs.catalog.cache import country_key_from_filename, invalidate_country_cache
from relocation_jobs.catalog.reads import (
    catalog_has_data,
    get_company,
    get_job_by_url,
    load_country_catalog,
    load_country_from_db,
)
from relocation_jobs.catalog.schema import init_catalog_schema
from relocation_jobs.catalog.stats import (
    load_catalog_stats,
    query_ats_distribution,
    query_company_stats_by_country,
    query_country_meta,
    query_empty_company_count,
    query_fetch_problem_companies,
    query_job_counts_by_country,
    query_latest_job_fetches_by_country,
)
from relocation_jobs.catalog.writes import (
    delete_company,
    insert_jobs,
    rename_company_in_catalog,
    save_country_catalog,
    touch_country_meta,
    update_company_fields,
    update_company_location,
    upsert_companies,
    upsert_company,
)

__all__ = [
    "catalog_has_data",
    "country_key_from_filename",
    "delete_company",
    "get_company",
    "get_job_by_url",
    "init_catalog_schema",
    "insert_jobs",
    "invalidate_country_cache",
    "load_catalog_stats",
    "load_country_catalog",
    "load_country_from_db",
    "query_ats_distribution",
    "query_company_stats_by_country",
    "query_country_meta",
    "query_empty_company_count",
    "query_fetch_problem_companies",
    "query_job_counts_by_country",
    "query_latest_job_fetches_by_country",
    "rename_company_in_catalog",
    "save_country_catalog",
    "touch_country_meta",
    "update_company_fields",
    "update_company_location",
    "upsert_companies",
    "upsert_company",
]
