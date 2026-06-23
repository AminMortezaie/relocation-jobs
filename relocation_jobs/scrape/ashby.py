"""Ashby job board scraper."""

from __future__ import annotations

import asyncio
import re

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.descriptions import html_to_text
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.relevance import is_relevant


def scrape_ashby(ats_url: str, *, playwright_fallback=None) -> list[dict]:
    from relocation_jobs.scrape.generic import scrape_with_playwright

    slug = ats_url.rstrip("/").split("/")[-1]
    api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        jobs = r.json().get("jobs", []) or []
        return [
            listing_job(
                j["title"],
                j.get("jobUrl", ats_url),
                location=j.get("location") or j.get("locationName"),
            )
            for j in jobs
            if is_relevant(j.get("title", ""))
        ]
    except Exception as e:
        print(f"    Ashby API error ({ats_url}): {e}")
        fallback = playwright_fallback or scrape_with_playwright
        return fallback(ats_url)


async def scrape_ashby_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
    playwright_fallback=None,
) -> list[dict]:
    from relocation_jobs.scrape.generic import scrape_with_playwright

    slug = ats_url.rstrip("/").split("/")[-1]
    api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = await client.get(api, timeout=10.0)
        r.raise_for_status()
        jobs = r.json().get("jobs", []) or []
        return [
            listing_job(
                j["title"],
                j.get("jobUrl", ats_url),
                location=j.get("location") or j.get("locationName"),
            )
            for j in jobs
            if (j.get("title") or "").strip()
        ]
    except Exception as e:
        print(f"    Ashby API error ({ats_url}): {e}")
        fallback = playwright_fallback or scrape_with_playwright
        return await asyncio.to_thread(
            fallback, ats_url, relevant_only=relevant_only
        )


def fetch_ashby_job_text(url: str) -> str:
    m = re.search(r"ashbyhq\.com/[^/]+/([0-9a-f-]{36})", url, re.I)
    if not m:
        return ""
    org_m = re.search(r"ashbyhq\.com/([^/]+)/", url, re.I)
    org = org_m.group(1) if org_m else ""
    if org:
        api = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensationRanges=true"
        try:
            r = requests.get(api, headers=HEADERS, timeout=10)
            if r.ok:
                for job in r.json().get("jobs", []) or []:
                    if job.get("id") == m.group(1) or m.group(1) in (job.get("jobUrl") or ""):
                        return html_to_text(job.get("descriptionHtml") or job.get("description") or "")
        except Exception:
            pass
    return ""
