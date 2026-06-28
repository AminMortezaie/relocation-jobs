from __future__ import annotations

import asyncio
from datetime import date

import httpx

from relocation_jobs.core.ats_detection import PLAYWRIGHT_AVAILABLE
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.fetch.log import log_event
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.descriptions import detect_visa_relocation, html_to_text
from relocation_jobs.scrape.job_text import fetch_job_description


def _today() -> str:
    return date.today().isoformat()


async def fetch_job_description_async(
    client: httpx.AsyncClient,
    url: str,
    ats_type: str | None = None,
) -> str:
    if ats_type in ("greenhouse", "greenhouse_eu", "lever", "lever_eu", "recruitee", "ashby"):
        return await run_sync(fetch_job_description, url, ats_type)
    try:
        response = await client.get(url, timeout=15.0)
        if response.is_success:
            text = html_to_text(response.text)
            if len(text) > 200:
                return text
    except Exception:
        pass
    if PLAYWRIGHT_AVAILABLE:
        return await run_sync(fetch_job_description, url, ats_type)
    return ""


async def enrich_one_job_async(
    client: httpx.AsyncClient,
    job: dict,
    ats_type: str | None,
    fetched: str,
    only_missing: bool,
) -> None:
    if only_missing and job.get("visa_sponsorship") is not None:
        return

    text = await fetch_job_description_async(client, job["url"], ats_type)
    job["visa_sponsorship"] = detect_visa_relocation(text)
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
