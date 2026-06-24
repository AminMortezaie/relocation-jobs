from __future__ import annotations

import json
import re
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.listing import listing_job


def bamboo_location_text(raw: dict | None) -> str:
    if not isinstance(raw, dict):
        return ""
    parts = [
        (raw.get("city") or "").strip(),
        (raw.get("region") or "").strip(),
        (raw.get("country") or "").strip(),
    ]
    return ", ".join(dict.fromkeys(part for part in parts if part))


def fetch_applicably_board_sync(board_url: str) -> list[dict]:
    response = requests.get(board_url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if "/apply/" not in href:
            continue
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug.lower() in ("apply", "jobs"):
            continue
        url = urljoin(board_url, href)
        if url in seen:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if len(title) < 3:
            continue
        seen.add(url)
        jobs.append(listing_job(title, url))
    return jobs


def fetch_bamboo_board_sync(api_url: str) -> list[dict]:
    url = api_url.rstrip("/")
    if not url.endswith("/list"):
        url = f"{url}/list" if url.endswith("/careers") else f"{url}/careers/list"
    response = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
    response.raise_for_status()
    base = url.rsplit("/list", 1)[0]
    jobs: list[dict] = []
    for item in response.json().get("result") or []:
        title = (item.get("jobOpeningName") or "").strip()
        job_id = item.get("id")
        if not title or not job_id:
            continue
        jobs.append(
            listing_job(
                title,
                f"{base}/{job_id}",
                location=bamboo_location_text(item.get("location")) or None,
            )
        )
    return jobs


def fetch_movingimage_board_sync(careers_url: str) -> list[dict]:
    base_url = careers_url.split("#", 1)[0].rstrip("/") or "https://www.movingimage.com/careers"
    response = requests.get(base_url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not re.search(r"/careers/[a-z0-9-]+", href, re.I):
            continue
        full = urljoin(base_url + "/", href)
        if full in seen or full.rstrip("/").endswith("/careers"):
            continue
        seen.add(full)
        try:
            page = requests.get(full, headers=HEADERS, timeout=12)
            if not page.ok:
                continue
            h1 = BeautifulSoup(page.text, "html.parser").find("h1")
            title = " ".join(h1.get_text(" ", strip=True).split()) if h1 else ""
        except Exception:
            title = ""
        if not title:
            slug = full.rstrip("/").split("/")[-1].replace("-", " ")
            title = slug.title()
        jobs.append(listing_job(title, full))
    return jobs


def fetch_project_a_board_sync(careers_url: str) -> list[dict]:
    board = careers_url.split("#", 1)[0].rstrip("/") or "https://www.project-a.vc/careers"
    response = requests.get(board, headers=HEADERS, timeout=15)
    response.raise_for_status()
    job_ids = list(dict.fromkeys(re.findall(r"/careers/(\d{6,})", response.text)))
    jobs: list[dict] = []
    for job_id in job_ids:
        job_url = f"https://www.project-a.vc/careers/{job_id}"
        try:
            page = requests.get(job_url, headers=HEADERS, timeout=12)
            if not page.ok:
                continue
            h1 = BeautifulSoup(page.text, "html.parser").find("h1")
            title = " ".join(h1.get_text(" ", strip=True).split()) if h1 else ""
        except Exception:
            title = ""
        if title:
            jobs.append(listing_job(title, job_url))
    return jobs


def fetch_hirehive_board_sync(ats_url: str) -> list[dict]:
    base = (ats_url or "").rstrip("/")
    api = base if base.endswith("/api/v1/jobs") else f"{base}/api/v1/jobs"
    response = requests.get(api, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return [
        listing_job((row.get("title") or "").strip(), row.get("hostedUrl") or base)
        for row in response.json().get("jobs", [])
        if (row.get("title") or "").strip()
    ]


def fetch_epam_board_sync(ats_url: str) -> list[dict]:
    board = (ats_url or "https://careers.epam.com/").rstrip("/") + "/"
    response = requests.get(board, headers=HEADERS, timeout=20)
    response.raise_for_status()
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.DOTALL)
    if not match:
        return []
    data = json.loads(match.group(1))
    raw = data.get("props", {}).get("pageProps", {}).get("initialJobs", {}).get("jobs", [])
    jobs: list[dict] = []
    for item in raw:
        seo = item.get("seo") or {}
        title = (item.get("name") or seo.get("title") or "").strip()
        title = re.sub(r"^Careers for\s+", "", title, flags=re.I)
        title = re.sub(r"\s*\|.*$", "", title).strip()
        path = (seo.get("url") or "").strip()
        if title and path:
            jobs.append(listing_job(title, urljoin("https://careers.epam.com", path)))
    return jobs


def fetch_rss_board_sync(feed_url: str) -> list[dict]:
    response = requests.get(feed_url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    text = response.text.lstrip("\ufeff").strip()
    xml_start = text.find("<?xml")
    if xml_start > 0:
        text = text[xml_start:]
    root = ElementTree.fromstring(text.encode("utf-8"))
    jobs: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            jobs.append(listing_job(title, link))
    return jobs


async def fetch_applytojob_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("careers_url") or "")
    return await run_sync(fetch_applicably_board_sync, url)


async def fetch_bamboo_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("careers_url") or "")
    return await run_sync(fetch_bamboo_board_sync, url)


async def fetch_movingimage_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("careers_url") or "")
    return await run_sync(fetch_movingimage_board_sync, url)


async def fetch_project_a_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("careers_url") or "")
    return await run_sync(fetch_project_a_board_sync, url)


async def fetch_hirehive_board(client, board_url: str, company: dict) -> list[dict]:
    return await run_sync(fetch_hirehive_board_sync, board_url)


async def fetch_epam_board(client, board_url: str, company: dict) -> list[dict]:
    return await run_sync(fetch_epam_board_sync, board_url)


async def fetch_rss_board(client, board_url: str, company: dict) -> list[dict]:
    return await run_sync(fetch_rss_board_sync, board_url)
