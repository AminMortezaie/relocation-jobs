from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.v2.scrape.listing import listing_job


def greenhouse_board_slug(ats_url: str) -> str:
    return ats_url.rstrip("/").split("/")[-1].split("?")[0]


def greenhouse_jobs_api_url(slug: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


async def fetch_greenhouse_board(client, board_url: str, company: dict) -> list[dict]:
    slug = greenhouse_board_slug(board_url)
    if not slug or slug in ("embed", "jobs", ""):
        return []
    response = await client.get(
        greenhouse_jobs_api_url(slug),
        headers=HEADERS,
        timeout=10.0,
    )
    response.raise_for_status()
    jobs: list[dict] = []
    for row in response.json().get("jobs") or []:
        title = (row.get("title") or "").strip()
        url = (row.get("absolute_url") or "").strip()
        if not title or not url:
            continue
        location = (row.get("location") or {}).get("name")
        jobs.append(listing_job(title, url, location=location))
    return jobs
