from __future__ import annotations

import json
import re

from relocation_jobs.core.ats_detection import HEADERS, _detect_deel_from_url
from relocation_jobs.v2.scrape.listing import listing_job

_DEEL_POSTING_PATTERNS = (
    re.compile(
        r'\\"id\\":\\"([a-f0-9-]+)\\",\\"jobId\\":\\"[a-f0-9-]+\\",\\"title\\":\\"((?:\\\\.|[^\\"])*)\\"',
        re.I,
    ),
    re.compile(
        r'"id":"([a-f0-9-]+)","jobId":"[a-f0-9-]+","title":"((?:\\.|[^"\\])*)"',
        re.I,
    ),
)


def deel_slug_from_url(board_url: str) -> str:
    match = re.search(r"jobs\.deel\.com/([a-zA-Z0-9_-]+)", board_url, re.I)
    return match.group(1) if match else board_url.rstrip("/").split("/")[-1].split("?")[0]


def parse_deel_jobs(html: str, slug: str) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for pattern in _DEEL_POSTING_PATTERNS:
        for match in pattern.finditer(html):
            posting_id = match.group(1)
            title = match.group(2).replace('\\"', '"').replace("\\\\", "\\").strip()
            if not posting_id or not title:
                continue
            url = f"https://jobs.deel.com/{slug}/job-details/{posting_id}/overview"
            if url in seen:
                continue
            seen.add(url)
            jobs.append(listing_job(title, url))
        if jobs:
            break
    return jobs


async def fetch_deel_board(client, board_url: str, company: dict) -> list[dict]:
    source = board_url or (company.get("careers_url") or "")
    detected = _detect_deel_from_url(source)
    fetch_url = detected[1] if detected[1] else ""
    if not fetch_url:
        return []
    slug = deel_slug_from_url(fetch_url)
    response = await client.get(fetch_url, headers=HEADERS, timeout=20.0)
    response.raise_for_status()
    return parse_deel_jobs(response.text, slug)
