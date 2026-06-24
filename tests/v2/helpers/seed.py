from __future__ import annotations

import json
from pathlib import Path

from relocation_jobs.core.db import db_transaction
from relocation_jobs.core.job_identity import job_idempotency_key, stamp_job_identity
from relocation_jobs.v2.catalog.repo import get_company
from relocation_jobs.v2.catalog.writes import save_company
from relocation_jobs.v2.scrape.merge import merge_matching_jobs


def seed_country(country_key: str, fixture_path: Path) -> dict:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    companies = data.get("companies") or []
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO country_meta (
                country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (country) DO UPDATE SET
                source = EXCLUDED.source,
                fetched = EXCLUDED.fetched,
                updated = EXCLUDED.updated,
                jobs_fetched = EXCLUDED.jobs_fetched,
                total = EXCLUDED.total,
                last_fetch_new_jobs = EXCLUDED.last_fetch_new_jobs
            """,
            (
                country_key,
                data.get("source") or "",
                data.get("fetched") or "",
                data.get("updated") or "",
                data.get("jobs_fetched") or "",
                data.get("total") or len(companies),
                int(data.get("last_fetch_new_jobs") or 0),
            ),
        )
    for company in companies:
        name = (company.get("name") or "").strip()
        if not name:
            continue
        blob = dict(company)
        for job in blob.get("matching_jobs") or []:
            stamp_job_identity(job)
            job.setdefault("idempotency_key", job_idempotency_key(job.get("url", "")))
        save_company(country_key, blob)
    return data


def replace_matching_jobs(country_key: str, company_name: str, jobs: list[dict]) -> None:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    company["matching_jobs"] = jobs
    save_company(country_key, company)


def merge_and_save_jobs(country_key: str, company_name: str, scraped: list[dict]) -> list[dict]:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    merged, _, _, _ = merge_matching_jobs(company.get("matching_jobs") or [], scraped)
    company["matching_jobs"] = merged
    save_company(country_key, company)
    return merged
