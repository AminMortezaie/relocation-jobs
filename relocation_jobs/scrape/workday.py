"""Workday CXS API scraper."""

from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS, _workday_api_and_base
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.relevance import is_relevant


def scrape_workday(ats_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Workday CXS API (myworkdayjobs.com / myworkdaysite.com)."""
    api, base = _workday_api_and_base(ats_url)
    if not api or not base:
        print(f"    Workday error ({ats_url}): missing API/base config")
        return []
    jobs: list[dict] = []
    offset = 0
    limit = 20
    total: int | None = None
    while offset <= 2000:
        try:
            r = requests.post(
                api,
                json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=25,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    Workday error ({api}): {e}")
            break
        postings = data.get("jobPostings") or []
        if total is None:
            total = int(data.get("total") or len(postings))
        for posting in postings:
            path = posting.get("externalPath") or ""
            title = posting.get("title") or ""
            if not path or not title:
                continue
            job_url = base.rstrip("/") + path
            if relevant_only and not is_relevant(title):
                continue
            jobs.append(listing_job(
                title,
                job_url,
                location=(posting.get("locationsText") or posting.get("location") or "").strip()
                or None,
            ))
        offset += limit
        if not postings or offset >= total:
            break
    if jobs:
        print(f"    Workday: {len(jobs)} role(s) from {total or '?'} posting(s)")
    return jobs


async def scrape_workday_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    api, base = _workday_api_and_base(ats_url)
    if not api or not base:
        print(f"    Workday error ({ats_url}): missing API/base config")
        return []
    jobs: list[dict] = []
    offset = 0
    limit = 20
    total: int | None = None
    while offset <= 2000:
        try:
            r = await client.post(
                api,
                json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=25.0,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    Workday error ({api}): {e}")
            break
        postings = data.get("jobPostings") or []
        if total is None:
            total = int(data.get("total") or len(postings))
        for posting in postings:
            path = posting.get("externalPath") or ""
            title = posting.get("title") or ""
            if not path or not title:
                continue
            job_url = base.rstrip("/") + path
            if relevant_only and not is_relevant(title):
                continue
            jobs.append(listing_job(
                title,
                job_url,
                location=(posting.get("locationsText") or posting.get("location") or "").strip()
                or None,
            ))
        offset += limit
        if not postings or offset >= total:
            break
    if jobs:
        print(f"    Workday: {len(jobs)} role(s) from {total or '?'} posting(s)")
    return jobs
