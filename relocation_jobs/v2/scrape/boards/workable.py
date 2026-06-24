from __future__ import annotations

import re

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.v2.scrape.listing import listing_job

_WORKABLE_POST_BODY = {
    "query": "",
    "location": [],
    "department": [],
    "worktype": [],
    "remote": [],
}


def workable_board_slug(ats_url: str) -> str:
    match = re.search(
        r"apply\.workable\.com/(?:api/v\d+/accounts/)?([a-z0-9-]+)",
        ats_url,
        re.I,
    )
    if match and match.group(1).lower() != "api":
        return match.group(1)
    return ""


def workable_jobs_api_url(slug: str) -> str:
    return f"https://apply.workable.com/api/v2/accounts/{slug}/jobs"


def workable_job_url(slug: str, shortcode: str) -> str:
    return f"https://apply.workable.com/{slug}/j/{shortcode}/"


def workable_location_text(raw: dict | None) -> str:
    if not isinstance(raw, dict):
        return ""
    parts = [
        (raw.get("city") or "").strip(),
        (raw.get("region") or "").strip(),
        (raw.get("country") or "").strip(),
    ]
    return ", ".join(dict.fromkeys(part for part in parts if part))


async def fetch_workable_board(client, board_url: str, company: dict) -> list[dict]:
    slug = workable_board_slug(board_url)
    if not slug:
        return []
    response = await client.post(
        workable_jobs_api_url(slug),
        json=_WORKABLE_POST_BODY,
        headers=HEADERS,
        timeout=10.0,
    )
    response.raise_for_status()
    jobs: list[dict] = []
    for row in response.json().get("results") or []:
        title = (row.get("title") or "").strip()
        shortcode = (row.get("shortcode") or "").strip()
        if not title or not shortcode:
            continue
        jobs.append(
            listing_job(
                title,
                workable_job_url(slug, shortcode),
                location=workable_location_text(row.get("location")),
            )
        )
    return jobs
