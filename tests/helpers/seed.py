from __future__ import annotations

import copy
import json
from pathlib import Path

from relocation_jobs.core.job_identity import job_idempotency_key, stamp_job_identity
from relocation_jobs.catalog.repo import get_company
from relocation_jobs.catalog.repo import sync_company_board_to_catalog
from relocation_jobs.catalog.repo import sync_country_catalog
from relocation_jobs.scrape.merge import merge_matching_jobs


def seed_country(country_key: str, fixture_path: Path) -> dict:
    data = copy.deepcopy(json.loads(fixture_path.read_text(encoding="utf-8")))
    for company in data.get("companies") or []:
        for job in company.get("matching_jobs") or []:
            stamp_job_identity(job)
            job.setdefault("idempotency_key", job_idempotency_key(job.get("url", "")))
    sync_country_catalog(country_key, data)
    return data


def replace_matching_jobs(country_key: str, company_name: str, jobs: list[dict]) -> None:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    company["matching_jobs"] = jobs
    sync_company_board_to_catalog(country_key, company)


def merge_and_save_jobs(country_key: str, company_name: str, scraped: list[dict]) -> list[dict]:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    merged, _, _, _, _ = merge_matching_jobs(company.get("matching_jobs") or [], scraped)
    company["matching_jobs"] = merged
    sync_company_board_to_catalog(country_key, company)
    return merged
