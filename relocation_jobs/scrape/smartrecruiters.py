"""SmartRecruiters job board scraper."""

from __future__ import annotations

from relocation_jobs.core.ats_detection import (
    HEADERS,
    _smartrecruiters_api_url,
    _smartrecruiters_company_id,
)
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job, smartrecruiters_location_text
from relocation_jobs.scrape.relevance import is_relevant


def scrape_smartrecruiters(ats_url: str) -> list[dict]:
    company_id = _smartrecruiters_company_id(ats_url)
    if not company_id:
        print(f"    SmartRecruiters error ({ats_url}): could not parse company id")
        return []
    jobs: list[dict] = []
    offset = 0
    try:
        while True:
            api = (
                f"{_smartrecruiters_api_url(company_id)}"
                f"?limit=100&offset={offset}&include=locations"
            )
            r = requests.get(api, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            content = data.get("content") or []
            for j in content:
                title = j.get("name") or ""
                if is_relevant(title):
                    jobs.append(listing_job(
                        title,
                        f"https://jobs.smartrecruiters.com/{company_id}/{j['id']}",
                        location=smartrecruiters_location_text(j.get("location")),
                    ))
            offset += len(content)
            total = data.get("totalFound", offset)
            if not content or offset >= total:
                break
        return jobs
    except Exception as e:
        print(f"    SmartRecruiters error ({ats_url}): {e}")
        return []


async def scrape_smartrecruiters_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    company_id = _smartrecruiters_company_id(ats_url)
    if not company_id:
        print(f"    SmartRecruiters error ({ats_url}): could not parse company id")
        return []
    jobs: list[dict] = []
    offset = 0
    try:
        while True:
            api = (
                f"{_smartrecruiters_api_url(company_id)}"
                f"?limit=100&offset={offset}&include=locations"
            )
            r = await client.get(api, timeout=15.0)
            r.raise_for_status()
            data = r.json()
            content = data.get("content") or []
            for j in content:
                title = (j.get("name") or "").strip()
                if not title:
                    continue
                if relevant_only and not is_relevant(title):
                    continue
                jobs.append(listing_job(
                    title,
                    f"https://jobs.smartrecruiters.com/{company_id}/{j['id']}",
                    location=smartrecruiters_location_text(j.get("location")),
                ))
            offset += len(content)
            total = data.get("totalFound", offset)
            if not content or offset >= total:
                break
        return jobs
    except Exception as e:
        print(f"    SmartRecruiters error ({ats_url}): {e}")
        return []
