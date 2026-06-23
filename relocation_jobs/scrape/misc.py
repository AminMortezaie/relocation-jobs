"""Miscellaneous career-page scrapers (HTML, RSS, Playwright)."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.listing import bamboohr_location_text, listing_job
from relocation_jobs.scrape.playwright import (
    PLAYWRIGHT_AVAILABLE,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
    sync_playwright,
)
from relocation_jobs.scrape.relevance import is_relevant


def scrape_applytojob(board_url: str, *, relevant_only: bool = True) -> list[dict]:
    """JazzHR / ApplyToJob boards list roles as /apply/{id}/{slug} links."""
    try:
        r = requests.get(board_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    ApplyToJob error ({board_url}): {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/apply/" not in href:
            continue
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug.lower() in ("apply", "jobs"):
            continue
        url = urljoin(board_url, href)
        if url in seen:
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        if len(title) < 3:
            continue
        seen.add(url)
        if relevant_only and not is_relevant(title):
            continue
        jobs.append({"title": title, "url": url})
    return jobs


def scrape_bamboohr(api_url: str, *, relevant_only: bool = True) -> list[dict]:
    """BambooHR public careers list JSON (e.g. wsd.bamboohr.com/careers/list)."""
    url = api_url.rstrip("/")
    if not url.endswith("/list"):
        url = f"{url}/list" if url.endswith("/careers") else f"{url}/careers/list"
    try:
        r = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"    BambooHR error ({api_url}): {e}")
        return []

    base = url.rsplit("/list", 1)[0]
    jobs: list[dict] = []
    for item in data.get("result") or []:
        title = (item.get("jobOpeningName") or "").strip()
        job_id = item.get("id")
        if not title or not job_id:
            continue
        if relevant_only and not is_relevant(title):
            continue
        location = bamboohr_location_text(item) or None
        jobs.append(listing_job(title, f"{base}/{job_id}", location=location))
    return jobs


def scrape_movingimage(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """movingimage.com hosts role pages under /careers/{slug}."""
    base_url = careers_url.split("#", 1)[0].rstrip("/") or "https://www.movingimage.com/careers"
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    movingimage error ({careers_url}): {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not re.search(r"/careers/[a-z0-9-]+", href, re.I):
            continue
        full = urljoin(base_url + "/", href)
        if full in seen or full.rstrip("/").endswith("/careers"):
            continue
        seen.add(full)
        try:
            pr = requests.get(full, headers=HEADERS, timeout=12)
            if not pr.ok:
                continue
            psoup = BeautifulSoup(pr.text, "html.parser")
            h1 = psoup.find("h1")
            title = " ".join(h1.get_text(" ", strip=True).split()) if h1 else ""
        except Exception:
            title = ""
        if not title:
            slug = full.rstrip("/").split("/")[-1].replace("-", " ")
            title = slug.title()
        if relevant_only and not is_relevant(title):
            continue
        jobs.append({"title": title, "url": full})
    return jobs


def scrape_project_a(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """project-a.vc lists numeric role pages at /careers/{id}."""
    board = careers_url.split("#", 1)[0].rstrip("/") or "https://www.project-a.vc/careers"
    try:
        r = requests.get(board, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    Project A error ({careers_url}): {e}")
        return []

    job_ids = list(dict.fromkeys(re.findall(r"/careers/(\d{6,})", r.text)))
    jobs: list[dict] = []
    for job_id in job_ids:
        job_url = f"https://www.project-a.vc/careers/{job_id}"
        try:
            pr = requests.get(job_url, headers=HEADERS, timeout=12)
            if not pr.ok:
                continue
            psoup = BeautifulSoup(pr.text, "html.parser")
            h1 = psoup.find("h1")
            title = " ".join(h1.get_text(" ", strip=True).split()) if h1 else ""
        except Exception:
            title = ""
        if not title:
            continue
        if relevant_only and not is_relevant(title):
            continue
        jobs.append({"title": title, "url": job_url})
    return jobs


def scrape_hirehive(ats_url: str, *, relevant_only: bool = True) -> list[dict]:
    base = (ats_url or "").rstrip("/")
    api = base if base.endswith("/api/v1/jobs") else f"{base}/api/v1/jobs"
    try:
        r = requests.get(api, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return [
            {"title": j["title"], "url": j.get("hostedUrl", base)}
            for j in r.json().get("jobs", [])
            if j.get("title") and (not relevant_only or is_relevant(j["title"]))
        ]
    except Exception as e:
        print(f"    HireHive error ({api}): {e}")
        return []


def scrape_epam(ats_url: str, *, relevant_only: bool = True) -> list[dict]:
    board = (ats_url or "https://careers.epam.com/").rstrip("/") + "/"
    try:
        r = requests.get(board, headers=HEADERS, timeout=20)
        r.raise_for_status()
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(1))
        raw = data.get("props", {}).get("pageProps", {}).get("initialJobs", {}).get("jobs", [])
        jobs: list[dict] = []
        for item in raw:
            seo = item.get("seo") or {}
            title = (item.get("name") or seo.get("title") or "").strip()
            title = re.sub(r"^Careers for\s+", "", title, flags=re.I)
            title = re.sub(r"\s*\|.*$", "", title).strip()
            path = seo.get("url") or ""
            if not title or not path:
                continue
            job_url = urljoin("https://careers.epam.com", path)
            if relevant_only and not is_relevant(title):
                continue
            jobs.append({"title": title, "url": job_url})
        return jobs
    except Exception as e:
        print(f"    EPAM error ({board}): {e}")
        return []


def scrape_rss(feed_url: str, *, relevant_only: bool = True) -> list[dict]:
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        text = r.text.lstrip("\ufeff").strip()
        xml_start = text.find("<?xml")
        if xml_start > 0:
            text = text[xml_start:]
        root = ElementTree.fromstring(text.encode("utf-8"))
        jobs: list[dict] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title or not link:
                continue
            if relevant_only and not is_relevant(title):
                continue
            jobs.append({"title": title, "url": link})
        return jobs
    except Exception as e:
        print(f"    RSS error ({feed_url}): {e}")
        return []


def scrape_jibe(
    careers_url: str,
    *,
    relevant_only: bool = True,
    playwright_available: bool | None = None,
    playwright_cm=None,
) -> list[dict]:
    """Booking.com / Jibe Angular job search (requires Playwright)."""
    pw_available = PLAYWRIGHT_AVAILABLE if playwright_available is None else playwright_available
    pw_cm = sync_playwright if playwright_cm is None else playwright_cm
    if not pw_available:
        return []
    merged: dict[str, str] = {}
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with pw_cm() as p:
                browser, context = _playwright_browser_context(p)
                page = context.new_page()
                page.goto(careers_url, wait_until="networkidle", timeout=90000)
                _playwright_pause(page, 5000)
                for _ in range(20):
                    raise_if_cancelled()
                    batch = page.evaluate(
                        """() => {
                          const out = [];
                          for (const a of document.querySelectorAll("a[href*='/jobs/']")) {
                            const h = a.href.split('?')[0];
                            const t = a.innerText.trim();
                            if (h.includes('login') || t.length < 5) continue;
                            if (!out.find(x => x.h === h)) out.push({h, t});
                          }
                          return out;
                        }"""
                    )
                    for row in batch:
                        merged[row["h"]] = row["t"]
                    next_btn = page.query_selector(
                        "button[aria-label='Next Page of Job Search Results']"
                    )
                    if not next_btn or next_btn.get_attribute("disabled"):
                        break
                    next_btn.click()
                    _playwright_pause(page, 4000)
                browser.close()
    except FetchCancelled:
        raise
    except Exception as e:
        print(f"    Jibe error ({careers_url}): {e}")
        return []
    jobs: list[dict] = []
    for url, title in merged.items():
        if relevant_only and not is_relevant(title):
            continue
        jobs.append({"title": title, "url": url})
    if jobs:
        print(f"    Jibe: {len(jobs)} role(s) across listing pages")
    return jobs


def scrape_atlassian(
    careers_url: str,
    *,
    relevant_only: bool = True,
    playwright_available: bool | None = None,
    playwright_cm=None,
) -> list[dict]:
    """Atlassian native careers board (JS-rendered detail links)."""
    pw_available = PLAYWRIGHT_AVAILABLE if playwright_available is None else playwright_available
    pw_cm = sync_playwright if playwright_cm is None else playwright_cm
    if not pw_available:
        return []
    merged: dict[str, str] = {}
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with pw_cm() as p:
                browser, context = _playwright_browser_context(p)
                page = context.new_page()
                page.goto(careers_url, wait_until="networkidle", timeout=90000)
                _playwright_pause(page, 8000)
                raise_if_cancelled()
                batch = page.evaluate(
                    """() => {
                      const out = [];
                      for (const a of document.querySelectorAll("a[href*='/careers/details/']")) {
                        const h = a.href.split('?')[0];
                        const t = a.innerText.trim();
                        if (t.length < 5) continue;
                        if (!out.find(x => x.h === h)) out.push({h, t});
                      }
                      return out;
                    }"""
                )
                for row in batch:
                    merged[row["h"]] = row["t"]
                browser.close()
    except FetchCancelled:
        raise
    except Exception as e:
        print(f"    Atlassian error ({careers_url}): {e}")
        return []
    jobs: list[dict] = []
    for url, title in merged.items():
        if relevant_only and not is_relevant(title):
            continue
        jobs.append({"title": title, "url": url})
    return jobs


async def scrape_hirehive_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    import asyncio
    return await asyncio.to_thread(scrape_hirehive, ats_url, relevant_only=relevant_only)


async def scrape_epam_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    import asyncio
    return await asyncio.to_thread(scrape_epam, ats_url, relevant_only=relevant_only)


async def scrape_rss_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    import asyncio
    return await asyncio.to_thread(scrape_rss, ats_url, relevant_only=relevant_only)
