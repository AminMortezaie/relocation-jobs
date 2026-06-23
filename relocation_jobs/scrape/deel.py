"""Deel job board scraper."""

from __future__ import annotations

import re

from relocation_jobs.core.ats_detection import HEADERS, _detect_deel_from_url
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.relevance import is_relevant

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
    m = re.search(r"jobs\.deel\.com/([a-zA-Z0-9_-]+)", board_url, re.I)
    return m.group(1) if m else board_url.rstrip("/").split("/")[-1].split("?")[0]


def parse_deel_jobs(html: str, slug: str, *, relevant_only: bool = True) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for pattern in _DEEL_POSTING_PATTERNS:
        for m in pattern.finditer(html):
            posting_id = m.group(1)
            title = m.group(2).replace('\\"', '"').replace("\\\\", "\\").strip()
            if not posting_id or not title:
                continue
            if relevant_only and not is_relevant(title):
                continue
            url = f"https://jobs.deel.com/{slug}/job-details/{posting_id}/overview"
            if url in seen:
                continue
            seen.add(url)
            jobs.append({"title": title, "url": url})
        if jobs:
            break
    return jobs


def scrape_deel(board_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Scrape jobs.deel.com boards from embedded jobPostings JSON."""
    detected = _detect_deel_from_url(board_url)
    if not detected[1]:
        return []
    fetch_url = detected[1]
    slug = deel_slug_from_url(fetch_url)

    try:
        r = requests.get(fetch_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"    Deel error ({fetch_url}): {e}")
        return []

    return parse_deel_jobs(r.text, slug, relevant_only=relevant_only)


async def scrape_deel_async(
    client: httpx.AsyncClient,
    board_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    detected = _detect_deel_from_url(board_url)
    if not detected[1]:
        return []
    fetch_url = detected[1]
    slug = deel_slug_from_url(fetch_url)

    try:
        r = await client.get(fetch_url, timeout=20.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Deel error ({fetch_url}): {e}")
        return []

    return parse_deel_jobs(r.text, slug, relevant_only=relevant_only)
