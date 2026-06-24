from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.listing import listing_job


def lever_board_slug(ats_url: str) -> str:
    return ats_url.rstrip("/").split("/")[-1].split("?")[0]


def lever_api_host(ats_url: str) -> str:
    return "jobs.eu.lever.co" if "eu.lever" in ats_url else "api.lever.co"


def lever_postings_api_url(slug: str, *, ats_url: str) -> str:
    host = lever_api_host(ats_url)
    return f"https://{host}/v0/postings/{slug}?mode=json"


async def fetch_lever_board(client, board_url: str, company: dict) -> list[dict]:
    slug = lever_board_slug(board_url)
    if not slug:
        return []
    response = await client.get(
        lever_postings_api_url(slug, ats_url=board_url),
        headers=HEADERS,
        timeout=10.0,
    )
    response.raise_for_status()
    jobs: list[dict] = []
    for row in response.json():
        title = (row.get("text") or "").strip()
        url = (row.get("hostedUrl") or board_url).strip()
        if not title or not url:
            continue
        location = (row.get("categories") or {}).get("location")
        jobs.append(listing_job(title, url, location=location))
    return jobs
