"""Workable job board scraper."""

from __future__ import annotations

import re

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job, workable_location_text
from relocation_jobs.scrape.relevance import is_relevant


def workable_slug_from_url(ats_url: str) -> str:
    m = re.search(r"apply\.workable\.com/(?:api/v\d+/accounts/)?([a-z0-9-]+)", ats_url, re.I)
    if m and m.group(1).lower() != "api":
        return m.group(1)
    return ""


def scrape_workable(ats_url: str) -> list[dict]:
    slug = workable_slug_from_url(ats_url)
    if not slug:
        print(f"    Workable error ({ats_url}): missing account slug")
        return []
    api = f"https://apply.workable.com/api/v2/accounts/{slug}/jobs"
    try:
        r = requests.post(
            api,
            json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
            headers=HEADERS, timeout=10,
        )
        r.raise_for_status()
        return [
            listing_job(
                j["title"],
                f"https://apply.workable.com/{slug}/j/{j['shortcode']}/",
                location=workable_location_text(j.get("location")),
            )
            for j in r.json().get("results", [])
            if is_relevant(j.get("title", ""))
        ]
    except Exception as e:
        print(f"    Workable error ({ats_url}): {e}")
        return []


async def scrape_workable_async(client: httpx.AsyncClient, ats_url: str) -> list[dict]:
    slug = workable_slug_from_url(ats_url)
    if not slug:
        print(f"    Workable error ({ats_url}): missing account slug")
        return []
    api = f"https://apply.workable.com/api/v2/accounts/{slug}/jobs"
    try:
        r = await client.post(
            api,
            json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
            timeout=10.0,
        )
        r.raise_for_status()
        return [
            listing_job(
                j["title"],
                f"https://apply.workable.com/{slug}/j/{j['shortcode']}/",
                location=workable_location_text(j.get("location")),
            )
            for j in r.json().get("results", [])
            if (j.get("title") or "").strip()
        ]
    except Exception as e:
        print(f"    Workable error ({ats_url}): {e}")
        return []
