from __future__ import annotations

from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
)


def find_job_in_data(data: dict, company_name: str, job_url: str) -> dict | None:
    target_url = normalize_job_url(job_url)
    target_key = job_idempotency_key(job_url)
    for company in data.get("companies", []):
        if company.get("name", "").lower() != company_name.lower():
            continue
        for job in company.get("matching_jobs") or []:
            if normalize_job_url(job.get("url", "")) == target_url:
                return job
            if target_key and job_idempotency_key_for_job(job) == target_key:
                return job
    return None
