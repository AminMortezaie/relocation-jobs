from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.listing import listing_job


def _personio_com_api(board_url: str) -> list[dict]:
    response = requests.get(
        board_url.rstrip("/"),
        headers={**HEADERS, "Accept": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    jobs: list[dict] = []
    for item in data:
        title = (item.get("name") or item.get("title") or "").strip()
        job_id = item.get("id") or ""
        if title and job_id:
            jobs.append(listing_job(title, f"https://www.personio.com/careers/{job_id}/"))
    return jobs


def _personio_xml_board(base: str) -> list[dict]:
    response = requests.get(f"{base}/xml", headers=HEADERS, timeout=10)
    body = (response.text or "").lstrip()
    if not (response.ok and body.startswith(("<?xml", "<workzag")) and len(response.content) >= 50):
        return []
    cleaned = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
        "&amp;",
        response.text,
    )
    root = ElementTree.fromstring(cleaned.encode())
    jobs: list[dict] = []
    for pos in root.findall("position"):
        title = (pos.findtext("name") or "").strip()
        job_id = (pos.findtext("id") or "").strip()
        office = (pos.findtext("office") or "").strip()
        if title and job_id:
            jobs.append(listing_job(title, f"{base}/job/{job_id}", location=office or None))
    return jobs


def _personio_html_board(base: str) -> list[dict]:
    response = requests.get(f"{base}/", headers=HEADERS, timeout=15)
    if not response.ok:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    seen: set[str] = set()
    jobs: list[dict] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/job/" not in href:
            continue
        full = urljoin(base + "/", href)
        if full in seen:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        h3 = anchor.find("h3") or anchor.find_previous("h3")
        if h3:
            title = " ".join(h3.get_text(" ", strip=True).split())
        if len(title) < 3:
            continue
        seen.add(full)
        jobs.append(listing_job(title, full))
    return jobs


def fetch_personio_board_sync(board_url: str) -> list[dict]:
    if "personio.com/api/careers/jobs" in board_url:
        return _personio_com_api(board_url)
    base = f"https://{urlparse(board_url).netloc}"
    jobs = _personio_xml_board(base)
    if jobs:
        return jobs
    return _personio_html_board(base)


async def fetch_personio_board(client, board_url: str, company: dict) -> list[dict]:
    return await run_sync(fetch_personio_board_sync, board_url)
