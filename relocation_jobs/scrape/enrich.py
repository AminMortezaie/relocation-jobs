"""Job description fetch and visa/relocation enrichment."""

from __future__ import annotations

import asyncio

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.scrape import descriptions as _scrape_descriptions
from relocation_jobs.scrape import greenhouse as _scrape_greenhouse
from relocation_jobs.scrape import lever as _scrape_lever
from relocation_jobs.scrape import recruitee as _scrape_recruitee
from relocation_jobs.scrape import ashby as _scrape_ashby
from relocation_jobs.scrape import http as _scrape_http
from relocation_jobs.scrape.shim_bind import scrape_jobs_shim
from relocation_jobs.scrape.util import today

requests = _scrape_http.requests
if HTTPX_AVAILABLE:
    httpx = _scrape_http.httpx

_html_to_text = _scrape_descriptions.html_to_text
detect_visa_relocation = _scrape_descriptions.detect_visa_relocation
_fetch_greenhouse_job_text = _scrape_greenhouse.fetch_greenhouse_job_text
_fetch_lever_job_text = _scrape_lever.fetch_lever_job_text
_fetch_recruitee_job_text = _scrape_recruitee.fetch_recruitee_job_text
_fetch_ashby_job_text = _scrape_ashby.fetch_ashby_job_text


def fetch_job_description(url: str, ats_type: str | None = None) -> str:
    """Fetch plain-text job description for visa/relocation checks."""
    sj = scrape_jobs_shim()
    fetchers = {
        "greenhouse": _fetch_greenhouse_job_text,
        "greenhouse_eu": _fetch_greenhouse_job_text,
        "lever": _fetch_lever_job_text,
        "lever_eu": _fetch_lever_job_text,
        "recruitee": _fetch_recruitee_job_text,
        "ashby": _fetch_ashby_job_text,
    }
    if ats_type in fetchers:
        text = fetchers[ats_type](url)
        if text:
            return text

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.ok:
            text = _html_to_text(r.text)
            if len(text) > 200:
                return text
    except Exception:
        pass

    if sj.PLAYWRIGHT_AVAILABLE:
        try:
            with sj.sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(2500)
                text = _html_to_text(page.content())
                browser.close()
                return text
        except Exception:
            pass
    return ""


def enrich_one_job(
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
    text = scrape_jobs_shim().fetch_job_description(job["url"], ats_type)
    job["visa_sponsorship"] = detect_visa_relocation(text)
    if not preserve_fetched or not job.get("fetched"):
        job["fetched"] = fetched


def enrich_jobs(
    jobs: list[dict],
    company: dict,
    only_missing: bool = False,
    *,
    workers: int = 4,
) -> list[dict]:
    """Sync wrapper — runs async enrichment on the event loop."""
    if not jobs:
        return jobs
    if not scrape_jobs_shim().HTTPX_AVAILABLE:
        for job in jobs:
            enrich_one_job(
                job, company.get("ats_type"), today(), only_missing,
                preserve_fetched=True,
            )
        return jobs

    async def _run() -> list[dict]:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=httpx.Timeout(15.0), follow_redirects=True
        ) as client:
            return await scrape_jobs_shim().enrich_jobs_async_with_client(
                client, jobs, company,
                only_missing=only_missing,
                concurrency=workers,
                preserve_fetched=False,
            )

    return asyncio.run(_run())


async def fetch_job_description_async(
    client: httpx.AsyncClient,
    url: str,
    ats_type: str | None = None,
) -> str:
    """Visa check text fetch — ATS helpers stay sync; generic page uses async HTTP."""
    sj = scrape_jobs_shim()
    if ats_type in ("greenhouse", "greenhouse_eu", "lever", "lever_eu", "recruitee", "ashby"):
        return await asyncio.to_thread(sj.fetch_job_description, url, ats_type)
    try:
        r = await client.get(url, timeout=15.0)
        if r.is_success:
            text = _html_to_text(r.text)
            if len(text) > 200:
                return text
    except Exception:
        pass
    if sj.PLAYWRIGHT_AVAILABLE:
        return await asyncio.to_thread(sj.fetch_job_description, url, ats_type)
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


async def enrich_jobs_async_with_client(
    client: httpx.AsyncClient,
    jobs: list[dict],
    company: dict,
    only_missing: bool = False,
    *,
    concurrency: int = 8,
    preserve_fetched: bool = False,
) -> list[dict]:
    if not jobs:
        return jobs
    ats_type = company.get("ats_type")
    fetched = today()
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
        await asyncio.gather(*(one(j) for j in jobs))
    except FetchCancelled:
        pass
    return jobs
