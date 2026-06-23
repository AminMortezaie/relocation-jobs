"""Recruitee job board scraper."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.descriptions import html_to_text
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.relevance import is_relevant


def scrape_recruitee(ats_url: str) -> list[dict]:
    parsed = urlparse(ats_url)
    slug = parsed.netloc.split(".")[0]
    api = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return [
            listing_job(
                o["title"],
                o.get("careers_url", ats_url),
                location=o.get("location")
                or ", ".join(
                    dict.fromkeys(
                        p for p in (
                            (o.get("city") or "").strip(),
                            (o.get("country") or "").strip(),
                        ) if p
                    )
                )
                or None,
            )
            for o in r.json().get("offers", [])
            if is_relevant(o.get("title", ""))
        ]
    except Exception as e:
        print(f"    Recruitee error ({ats_url}): {e}")
        return []


async def scrape_recruitee_async(client: httpx.AsyncClient, ats_url: str) -> list[dict]:
    parsed = urlparse(ats_url)
    slug = parsed.netloc.split(".")[0]
    api = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = await client.get(api, timeout=10.0)
        r.raise_for_status()
        return [
            listing_job(
                o["title"],
                o.get("careers_url", ats_url),
                location=o.get("location")
                or ", ".join(
                    dict.fromkeys(
                        p for p in (
                            (o.get("city") or "").strip(),
                            (o.get("country") or "").strip(),
                        ) if p
                    )
                )
                or None,
            )
            for o in r.json().get("offers", [])
            if (o.get("title") or "").strip()
        ]
    except Exception as e:
        print(f"    Recruitee error ({ats_url}): {e}")
        return []


def fetch_recruitee_job_text(url: str) -> str:
    m = re.search(r"([a-z0-9-]+)\.recruitee\.com/o/([a-z0-9-]+)", url, re.I)
    if not m:
        return ""
    company, offer_slug = m.group(1), m.group(2)
    try:
        r = requests.get(f"https://{company}.recruitee.com/api/offers/", headers=HEADERS, timeout=10)
        r.raise_for_status()
        for offer in r.json().get("offers", []):
            if offer.get("slug") == offer_slug:
                detail = requests.get(
                    f"https://{company}.recruitee.com/api/offers/{offer['id']}",
                    headers=HEADERS, timeout=10,
                )
                if detail.ok:
                    desc = detail.json().get("offer", {}).get("description", "")
                    return html_to_text(desc)
    except Exception:
        pass
    return ""
