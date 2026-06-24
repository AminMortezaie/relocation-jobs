from __future__ import annotations

from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
)


def find_job_in_data(data: dict, company_name: str, job_url: str) -> dict | None:
    target_url = normalize_job_url(job_url)
    target_key = job_idempotency_key(job_url)
    company_jobs: list[dict] = []
    for company in data.get("companies", []):
        if company.get("name", "").lower() != company_name.lower():
            continue
        company_jobs = list(company.get("matching_jobs") or [])
        break
    for job in company_jobs:
        if normalize_job_url(job.get("url", "")) == target_url:
            return job
    if target_key:
        key_matches = [
            job for job in company_jobs
            if job_idempotency_key_for_job(job) == target_key
        ]
        if len(key_matches) == 1:
            return key_matches[0]
    return None
