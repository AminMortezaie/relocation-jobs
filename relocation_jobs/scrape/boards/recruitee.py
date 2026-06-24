from __future__ import annotations

from urllib.parse import urlparse

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.listing import listing_job


def recruitee_board_slug(ats_url: str) -> str:
    return urlparse(ats_url).netloc.split(".")[0]


def recruitee_offers_api_url(slug: str) -> str:
    return f"https://{slug}.recruitee.com/api/offers/"


def recruitee_offer_location(offer: dict) -> str | None:
    location = (offer.get("location") or "").strip()
    if location:
        return location
    parts = [
        (offer.get("city") or "").strip(),
        (offer.get("country") or "").strip(),
    ]
    text = ", ".join(dict.fromkeys(part for part in parts if part))
    return text or None


async def fetch_recruitee_board(client, board_url: str, company: dict) -> list[dict]:
    slug = recruitee_board_slug(board_url)
    if not slug:
        return []
    response = await client.get(
        recruitee_offers_api_url(slug),
        headers=HEADERS,
        timeout=10.0,
    )
    response.raise_for_status()
    jobs: list[dict] = []
    for row in response.json().get("offers") or []:
        title = (row.get("title") or "").strip()
        url = (row.get("careers_url") or board_url).strip()
        if not title or not url:
            continue
        jobs.append(listing_job(title, url, location=recruitee_offer_location(row)))
    return jobs
