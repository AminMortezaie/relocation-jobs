"""Greenhouse job board scraper."""

from __future__ import annotations

import re

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.descriptions import html_to_text
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.relevance import is_relevant


def scrape_greenhouse(ats_url: str) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
    if not slug or slug in ("embed", "jobs", ""):
        return []
    api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return [
            listing_job(
                j["title"],
                j["absolute_url"],
                location=(j.get("location") or {}).get("name"),
            )
            for j in r.json().get("jobs", [])
            if is_relevant(j.get("title", ""))
        ]
    except Exception as e:
        print(f"    Greenhouse error ({ats_url}): {e}")
        return []


async def scrape_greenhouse_async(
    client: httpx.AsyncClient, ats_url: str, *, eu: bool = False
) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
    if not slug or slug in ("embed", "jobs", ""):
        return []
    # EU job boards (boards.eu.greenhouse.io) still use the US API host.
    api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = await client.get(api, timeout=10.0)
        r.raise_for_status()
        return [
            listing_job(
                j["title"],
                j["absolute_url"],
                location=(j.get("location") or {}).get("name"),
            )
            for j in r.json().get("jobs", [])
            if (j.get("title") or "").strip()
        ]
    except Exception as e:
        label = "Greenhouse EU" if eu else "Greenhouse"
        print(f"    {label} error ({ats_url}): {e}")
        return []


def fetch_greenhouse_job_text(url: str) -> str:
    m = re.search(r"greenhouse\.io/(?:[^/]+/)?jobs/(\d+)", url, re.I)
    if not m:
        return ""
    job_id = m.group(1)
    m_board = re.search(r"greenhouse\.io/([^/]+)/jobs/", url, re.I)
    slug = m_board.group(1) if m_board else ""
    for board in [slug, "monzo", ""]:
        if not board:
            continue
        api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        try:
            r = requests.get(api, headers=HEADERS, timeout=10)
            if r.ok and r.json().get("content"):
                return html_to_text(r.json()["content"])
        except Exception:
            pass
    return ""
