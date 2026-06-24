from __future__ import annotations

import asyncio
from datetime import date

import httpx

from relocation_jobs.core.ats_detection import HEADERS, PLAYWRIGHT_AVAILABLE
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.v2.scrape.boards._async import run_sync
from relocation_jobs.v2.scrape.descriptions import detect_visa_relocation, html_to_text
from relocation_jobs.v2.scrape.job_text import fetch_job_description


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
    *,
    preserve_fetched: bool = False,
) -> None:
    if preserve_fetched and job.get("fetched"):
        if only_missing and job.get("visa_sponsorship") is not None:
            return
        if only_missing:
            return
    elif only_missing and job.get("visa_sponsorship") is not None:
        if not preserve_fetched:
            job["fetched"] = fetched
        return
    text = await fetch_job_description_async(client, job["url"], ats_type)
    job["visa_sponsorship"] = detect_visa_relocation(text)
    if not preserve_fetched or not job.get("fetched"):
        job["fetched"] = fetched


async def enrich_jobs(
    client: httpx.AsyncClient,
    jobs: list[dict],
    company: dict,
    *,
    only_missing: bool = False,
    concurrency: int = 8,
    preserve_fetched: bool = False,
) -> list[dict]:
    if not jobs:
        return jobs
    ats_type = company.get("ats_type")
    fetched = _today()
    sem = asyncio.Semaphore(max(1, min(concurrency, len(jobs))))

    async def one(job: dict) -> None:
        raise_if_cancelled()
        async with sem:
            raise_if_cancelled()
            await enrich_one_job_async(
                client, job, ats_type, fetched, only_missing,
                preserve_fetched=preserve_fetched,
            )

    try:
        await asyncio.gather(*(one(job) for job in jobs))
    except FetchCancelled:
        pass
    return jobs
