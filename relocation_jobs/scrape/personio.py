"""Personio job board scraper."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.relevance import is_relevant


def scrape_personio_com_api(api_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Personio's own careers site (personio.com) — JSON list API, not *.jobs.personio.de."""
    url = api_url.rstrip("/")
    try:
        r = requests.get(
            url,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        jobs = []
        for item in data:
            title = item.get("name") or item.get("title") or ""
            job_id = item.get("id") or ""
            if job_id and (not relevant_only or is_relevant(title)):
                jobs.append({
                    "title": title,
                    "url": f"https://www.personio.com/careers/{job_id}/",
                })
        return jobs
    except Exception as e:
        print(f"    Personio API error ({api_url}): {e}")
        return []


def scrape_personio_html(base: str, *, relevant_only: bool = True) -> list[dict]:
    """Fallback when Personio /xml feed is disabled (common on newer boards)."""
    try:
        r = requests.get(f"{base}/", headers=HEADERS, timeout=15)
        if not r.ok:
            return []
    except Exception as e:
        print(f"    Personio HTML error ({base}): {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    seen: set[str] = set()
    jobs = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/job/" not in href:
            continue
        full = urljoin(base + "/", href)
        if full in seen:
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        h3 = a.find("h3") or a.find_previous("h3")
        if h3:
            title = " ".join(h3.get_text(" ", strip=True).split())
        if len(title) < 3:
            continue
        if not relevant_only or is_relevant(title):
            seen.add(full)
            jobs.append({"title": title, "url": full})

    return jobs


def scrape_personio(ats_url: str, *, relevant_only: bool = True, html_scraper=None) -> list[dict]:
    html_fetch = html_scraper or scrape_personio_html
    if "personio.com/api/careers/jobs" in ats_url:
        return scrape_personio_com_api(ats_url, relevant_only=relevant_only)

    parsed = urlparse(ats_url)
    base = f"https://{parsed.netloc}"
    xml_url = f"{base}/xml"
    try:
        r = requests.get(xml_url, headers=HEADERS, timeout=10)
        body = (r.text or "").lstrip()
        is_xml = r.ok and body.startswith(("<?xml", "<workzag"))
        if is_xml and len(r.content) >= 50:
            try:
                from lxml import etree
                root = etree.fromstring(r.content, parser=etree.XMLParser(recover=True))
                positions = root.findall(".//position")
            except ImportError:
                cleaned = re.sub(
                    r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', r.text
                )
                root = ElementTree.fromstring(cleaned.encode())
                positions = root.findall("position")
            jobs = []
            for pos in positions:
                title = pos.findtext("name") or ""
                job_id = pos.findtext("id") or ""
                office = (pos.findtext("office") or "").strip()
                if job_id and (not relevant_only or is_relevant(title)):
                    jobs.append(listing_job(
                        title,
                        f"{base}/job/{job_id}",
                        location=office or None,
                    ))
            if jobs:
                return jobs
    except Exception as e:
        print(f"    Personio XML error ({ats_url}): {e}")

    jobs = html_fetch(base, relevant_only=relevant_only)
    if jobs:
        print(f"    Personio XML unavailable, parsed {len(jobs)} job(s) from HTML")
    return jobs


async def scrape_personio_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    import asyncio
    return await asyncio.to_thread(scrape_personio, ats_url, relevant_only=relevant_only)
