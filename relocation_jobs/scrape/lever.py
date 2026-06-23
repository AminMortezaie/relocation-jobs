"""Lever job board scraper."""

from __future__ import annotations

import re

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.descriptions import html_to_text
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.relevance import is_relevant


def scrape_lever(ats_url: str) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1]
    is_eu = "eu.lever" in ats_url
    api_host = "jobs.eu.lever.co" if is_eu else "api.lever.co"
    api = f"https://{api_host}/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return [
            listing_job(
                j["text"],
                j.get("hostedUrl", ats_url),
                location=(j.get("categories") or {}).get("location"),
            )
            for j in r.json()
            if is_relevant(j.get("text", ""))
        ]
    except Exception as e:
        print(f"    Lever error ({ats_url}): {e}")
        return []


async def scrape_lever_async(client: httpx.AsyncClient, ats_url: str) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1]
    is_eu = "eu.lever" in ats_url
    api_host = "jobs.eu.lever.co" if is_eu else "api.lever.co"
    api = f"https://{api_host}/v0/postings/{slug}?mode=json"
    try:
        r = await client.get(api, timeout=10.0)
        r.raise_for_status()
        return [
            listing_job(
                j["text"],
                j.get("hostedUrl", ats_url),
                location=(j.get("categories") or {}).get("location"),
            )
            for j in r.json()
            if (j.get("text") or "").strip()
        ]
    except Exception as e:
        print(f"    Lever error ({ats_url}): {e}")
        return []


def fetch_lever_job_text(url: str) -> str:
    m = re.search(r"lever\.co/[^/]+/([0-9a-f-]{36})", url, re.I)
    if not m:
        return ""
    api = f"https://api.lever.co/v0/postings/{m.group(1)}"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        if not r.ok:
            return ""
        data = r.json()
        parts = [
            data.get("descriptionPlain") or "",
            data.get("description") or "",
            str(data.get("lists") or ""),
            str(data.get("additional") or ""),
        ]
        return html_to_text("\n".join(parts))
    except Exception:
        return ""
