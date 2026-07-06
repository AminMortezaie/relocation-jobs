from __future__ import annotations

import asyncio
from datetime import date

import httpx

from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.fetch.log import log_event
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.descriptions import detect_visa_relocation
from relocation_jobs.scrape.job_text import fetch_job_description
from relocation_jobs.scrape.merge import job_has_listing_location


def _today() -> str:
    return date.today().isoformat()


def _job_enrichment_complete(job: dict) -> bool:
    has_visa = job.get("visa_sponsorship") is not None
    has_desc = bool((job.get("description_text") or "").strip())
    has_location = job_has_listing_location(job)
    return has_visa and has_desc and has_location


async def fetch_job_description_async(
    client: httpx.AsyncClient,
    url: str,
    ats_type: str | None = None,
) -> str:
    return await run_sync(fetch_job_description, url, ats_type)


async def enrich_one_job_async(
    client: httpx.AsyncClient,
    job: dict,
    ats_type: str | None,
    fetched: str,
    only_missing: bool,
) -> None:
    if only_missing and _job_enrichment_complete(job):
        return

    text = await fetch_job_description_async(client, job["url"], ats_type)
    job["visa_sponsorship"] = detect_visa_relocation(text)
    stripped = (text or "").strip()
    if stripped:
        job["description_text"] = stripped
    if not (job.get("fetched") or "").strip():
        job["fetched"] = fetched


async def enrich_jobs(
    client: httpx.AsyncClient,
    jobs: list[dict],
    company: dict,
    *,
    only_missing: bool = False,
    concurrency: int = 8,
) -> list[dict]:
    if not jobs:
        return jobs
    ats_type = company.get("ats_type")
    fetched = _today()
    name = (company.get("name") or "").strip()
    log_event(f"enriching {len(jobs)} job(s)", company=name)
    sem = asyncio.Semaphore(max(1, min(concurrency, len(jobs))))

    async def one(job: dict) -> None:
        raise_if_cancelled()
        async with sem:
            raise_if_cancelled()
            await enrich_one_job_async(
                client, job, ats_type, fetched, only_missing,
            )

    try:
        await asyncio.gather(*(one(job) for job in jobs))
    except FetchCancelled:
        pass
    return jobs
