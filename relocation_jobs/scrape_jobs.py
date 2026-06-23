#!/usr/bin/env python3
"""
Scrape careers pages from germany_companies.json and find matching backend jobs.

Strategy
--------
ATS type and URL are cached per company in the JSON (fields: ats_type, ats_url).
On the first run (or when cache is missing) the scraper loads the careers page in
Playwright and intercepts every XHR/fetch call to auto-detect the ATS. The
discovered values are written back to the JSON so subsequent runs use the fast
REST API directly — no Playwright needed unless the cache is empty.

To force re-detection for a company, delete its ats_type / ats_url fields from
the JSON and re-run.

Install deps:
    pip install requests httpx beautifulsoup4 playwright lxml
    python3 -m playwright install chromium

Run (full):
    python3 scripts/scrape_jobs.py

Run (single company):
    python3 scripts/scrape_jobs.py "HelloFresh"

Run (skip already-scraped companies):
    python3 scripts/scrape_jobs.py --skip-filled

Run (concurrent — asyncio event loop, default 16 in-flight companies):
    python3 scripts/scrape_jobs.py --file netherlands_companies.json --workers 16

Run (sequential, one company at a time):
    python3 scripts/scrape_jobs.py --file netherlands_companies.json --serial
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from relocation_jobs.core.ats_constants import (
    ATS_TYPE_CHOICES,
    BOL_CAREERS_API,
    DEFAULT_CONCURRENCY,
    EXCLUDE_KEYWORDS,
    FORCE_KNOWN_ATS,
    HTTPX_AVAILABLE,
    INCLUDE_KEYWORDS,
    KNOWN_ATS,
)

if HTTPX_AVAILABLE:
    import httpx

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # type: ignore[misc, assignment]

from relocation_jobs.core.paths import COUNTRY_FILE_NAMES
from relocation_jobs.catalog_db import (
    load_country,
    touch_country_meta,
    upsert_company,
)
from relocation_jobs.core.job_identity import job_idempotency_key, job_idempotency_key_for_job, stamp_job_identity
from relocation_jobs.core.location_tags import (
    company_expected_locations,
    filter_jobs_by_expected_locations,
    job_matches_expected_locations,
)

from relocation_jobs.core.ats_detection import (
    ATS_HINT_URL_DETECTORS,
    HTML_ATS_PATTERNS,
    HEADERS,
    PLAYWRIGHT_AVAILABLE,
    XHR_ATS_PATTERNS,
    _detect_ats_from_careers_url,
    _detect_deel_from_url,
    _detect_join_from_url,
    _detect_applytojob_from_url,
    _detect_bamboohr_from_url,
    _detect_hirehive_from_url,
    _detect_job_shop_from_url,
    _detect_recruitee_board_url,
    _detect_recruitee_from_careers_host,
    _detect_smartrecruiters_from_careers_url,
    _detect_smartrecruiters_from_redcare_careers,
    _detect_teamtailor_from_url,
    _detect_workday_from_url,
    _extract_ashby,
    _extract_greenhouse,
    _extract_greenhouse_eu,
    _extract_lever,
    _extract_personio,
    _extract_recruitee,
    _extract_smartrecruiters,
    _extract_teamtailor,
    _extract_workable,
    _extract_workday,
    _company_slug,
    _detect_ats_in_html_for_hint,
    _CAREERS_PAGE_AS_ATS,
    _parse_job_shop_config,
    _resolve_nuxt_payload_node,
    _resolve_nuxt_scalar,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
    _smartrecruiters_api_url,
    _smartrecruiters_company_id,
    _workday_api_and_base,
    detect_ats_for_hint,
    detect_ats_static,
    detect_ats_static_async,
    detect_ats_via_playwright,
    guess_ats_url_from_name,
)
from relocation_jobs.core.scrape_cancel import (
    FetchCancelled,
    clear_cancel_checker,
    is_cancel_requested,
    raise_if_cancelled,
    set_cancel_checker,
)


# Concurrent in-flight tasks (asyncio), not OS threads or processes
DEFAULT_WORKERS = DEFAULT_CONCURRENCY  # CLI alias: --workers
_print_lock = threading.Lock()
# Playwright launches Chromium; cap concurrent browsers during bulk fetch.

def _safe_print(*args, **kwargs) -> None:
    with _print_lock:
        print(*args, **kwargs)


def today() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    """UTC timestamp for fetch ordering (same-day refetches sort correctly)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _filter_relevant_jobs(jobs: list[dict], relevant_only: bool) -> list[dict]:
    """Drop empty titles; optionally keep only titles that pass keyword filters."""
    out: list[dict] = []
    for job in jobs:
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()
        if not title or not url:
            continue
        if relevant_only and not is_relevant(title):
            continue
        entry = {"title": title, "url": url}
        if job.get("location") is not None:
            entry["location"] = job["location"]
        if job.get("locations") is not None:
            entry["locations"] = job["locations"]
        out.append(entry)
    return out


def _listing_job(
    title: str,
    url: str,
    *,
    location: str | dict | None = None,
    locations: list | None = None,
) -> dict:
    job = {"title": title, "url": url}
    if location is not None and location != "":
        job["location"] = location
    if locations:
        job["locations"] = locations
    return job


def _workable_location_text(raw: dict | None) -> str:
    if not isinstance(raw, dict):
        return ""
    parts = [
        (raw.get("city") or "").strip(),
        (raw.get("region") or "").strip(),
        (raw.get("country") or "").strip(),
    ]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def _smartrecruiters_location_text(raw: dict | None) -> str:
    if not isinstance(raw, dict):
        return ""
    full = (raw.get("fullLocation") or raw.get("full_location") or "").strip()
    if full:
        return full
    parts = [(raw.get("city") or "").strip(), (raw.get("country") or "").strip()]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def _bamboohr_location_text(item: dict) -> str:
    """Location from BambooHR careers/list JSON row."""
    loc = item.get("location")
    if isinstance(loc, dict):
        parts = [
            (loc.get("city") or "").strip(),
            (loc.get("state") or "").strip(),
            (loc.get("addressCountry") or loc.get("country") or "").strip(),
        ]
        text = ", ".join(dict.fromkeys(p for p in parts if p))
        if text:
            return text
    ats = item.get("atsLocation")
    if isinstance(ats, dict):
        parts = [
            (ats.get("city") or "").strip(),
            (ats.get("state") or ats.get("province") or "").strip(),
            (ats.get("country") or "").strip(),
        ]
        text = ", ".join(dict.fromkeys(p for p in parts if p))
        if text:
            return text
    if item.get("isRemote"):
        return "Remote"
    return ""


def is_relevant(title: str) -> bool:
    t = title.lower()
    if re.search(r"\bchief technology officer\b|\bcto\b", t):
        return False
    has_include = any(kw in t for kw in INCLUDE_KEYWORDS)
    if not has_include:
        return False

    # "Marketing" etc. often labels the team, not the role (e.g. Fullstack Engineer – Marketing).
    if re.search(r"\b(engineer|developer|programmer)\b", t):
        excludes = [kw for kw in EXCLUDE_KEYWORDS if kw.strip() != "marketing"]
    else:
        excludes = EXCLUDE_KEYWORDS

    if any(kw in t for kw in excludes):
        return False
    # "Senior/Staff Product Engineer" is a level range, not a Staff-only role.
    if re.search(r"\bstaff\b", t) and not re.search(r"senior\s*/\s*staff", t):
        return False
    if "cloud engineer" in t and "backend" not in t and "software" not in t:
        return False
    if "ai platform" in t and "backend" not in t and "software" not in t:
        return False
    return True


def explain_title_filter(title: str) -> str:
    """Human-readable reason when ``is_relevant`` rejects a title."""
    t = (title or "").lower()
    if re.search(r"\bchief technology officer\b|\bcto\b", t):
        return "Title excluded (CTO)"
    if not any(kw in t for kw in INCLUDE_KEYWORDS):
        return "Title not relevant (no backend/software keyword)"
    if re.search(r"\b(engineer|developer|programmer)\b", t):
        excludes = [kw for kw in EXCLUDE_KEYWORDS if kw.strip() != "marketing"]
    else:
        excludes = EXCLUDE_KEYWORDS
    for kw in excludes:
        if kw in t:
            label = kw.strip() or kw
            return f"Title excluded ({label})"
    if re.search(r"\bstaff\b", t) and not re.search(r"senior\s*/\s*staff", t):
        return "Title excluded (staff level)"
    if "cloud engineer" in t and "backend" not in t and "software" not in t:
        return "Title excluded (cloud engineer without backend/software)"
    if "ai platform" in t and "backend" not in t and "software" not in t:
        return "Title excluded (AI platform without backend/software)"
    return "Title not relevant"


GENERIC_LINK_LABELS = frozenset({
    "view job", "view role", "view position", "see job", "see role",
    "apply", "apply now", "read more", "learn more", "details",
})

JOB_DETAIL_PATH = re.compile(r"/job[s]?/", re.I)
_LISTING_NOISE_URL = re.compile(r"/jobs/show_more\b", re.I)
_JUNK_LISTING_TITLE = re.compile(
    r"^(show\s+\d+\s+more|load\s+more|view\s+all(\s+jobs)?|see\s+all(\s+jobs)?)$",
    re.I,
)


def _normalize_title(text: str) -> str:
    return " ".join((text or "").split())


def _title_from_listing_anchor(a) -> str:
    """Best-effort title from a listing-page job link."""
    title = _normalize_title(a.get_text(" ", strip=True))
    if title.lower() not in GENERIC_LINK_LABELS and len(title) >= 5:
        if "job family" not in title.lower():
            return title[:150]

    node = a.parent
    best = ""
    for _ in range(8):
        if not node:
            break
        t = _normalize_title(node.get_text(" ", strip=True))
        lower = t.lower()
        if "job family" in lower:
            t = re.split(r"job family", t, maxsplit=1, flags=re.I)[0].strip()
        if len(t) > len(best):
            best = t
        node = node.parent
    return best[:150]


def _fetch_job_detail_title(url: str) -> str:
    """Load a job detail page and read the real title (h1 / og:title)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code >= 400:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        h1 = soup.find("h1")
        if h1:
            t = _normalize_title(h1.get_text(" ", strip=True))
            if t:
                return t[:150]
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            t = _normalize_title(og["content"])
            t = re.sub(r"\s*[-|–]\s*[^-|–]+ careers\s*$", "", t, flags=re.I)
            return t[:150]
    except Exception:
        pass
    return ""


def _needs_detail_title(guess: str) -> bool:
    t = _normalize_title(guess).lower()
    if not t or t in GENERIC_LINK_LABELS or len(t) < 5:
        return True
    if "job family" in t and len(guess) > 80:
        return True
    if not is_relevant(guess):
        return True
    return False


def _is_listing_noise_url(url: str) -> bool:
    return bool(_LISTING_NOISE_URL.search(url or ""))


def _collect_listing_job_links(soup, page_url: str) -> dict[str, str]:
    candidates: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        full_url = urljoin(page_url, a["href"])
        if full_url.rstrip("/") == page_url.rstrip("/"):
            continue
        if _is_listing_noise_url(full_url):
            continue
        if not JOB_DETAIL_PATH.search(full_url):
            continue
        guess = _title_from_listing_anchor(a)
        if _JUNK_LISTING_TITLE.match(_normalize_title(guess)):
            continue
        prev = candidates.get(full_url)
        if not prev or len(guess) > len(prev):
            candidates[full_url] = guess
    return candidates


def _listing_candidates_to_jobs(
    candidates: dict[str, str],
    *,
    relevant_only: bool = True,
) -> list[dict]:
    jobs: list[dict] = []
    for job_url, guess in candidates.items():
        if _is_listing_noise_url(job_url):
            continue
        title = _normalize_title(guess)
        if _needs_detail_title(guess):
            detail = _fetch_job_detail_title(job_url)
            if detail:
                title = detail
        if len(title) < 5 or len(title) > 150:
            continue
        if _JUNK_LISTING_TITLE.match(title):
            continue
        if relevant_only and not is_relevant(title):
            continue
        jobs.append({"title": title, "url": job_url})
    return jobs


def _jobs_from_listing_html(
    html: str,
    page_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = _collect_listing_job_links(soup, page_url)
    return _listing_candidates_to_jobs(candidates, relevant_only=relevant_only)


async def _jobs_from_listing_html_async(
    html: str,
    page_url: str,
    client: httpx.AsyncClient,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = _collect_listing_job_links(soup, page_url)
    jobs: list[dict] = []

    async def resolve_one(job_url: str, guess: str) -> dict | None:
        title = _normalize_title(guess)
        if _needs_detail_title(guess):
            detail = await asyncio.to_thread(_fetch_job_detail_title, job_url)
            if detail:
                title = detail
        if len(title) < 5 or len(title) > 150:
            return None
        if relevant_only and not is_relevant(title):
            return None
        return {"title": title, "url": job_url}

    if not candidates:
        return jobs

    sem = asyncio.Semaphore(8)

    async def bounded(item: tuple[str, str]) -> dict | None:
        async with sem:
            return await resolve_one(item[0], item[1])

    results = await asyncio.gather(*(bounded(x) for x in candidates.items()))
    return [j for j in results if j]


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


def _deel_slug_from_url(board_url: str) -> str:
    m = re.search(r"jobs\.deel\.com/([a-zA-Z0-9_-]+)", board_url, re.I)
    return m.group(1) if m else board_url.rstrip("/").split("/")[-1].split("?")[0]


def _parse_deel_jobs(html: str, slug: str, *, relevant_only: bool = True) -> list[dict]:
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
    slug = _deel_slug_from_url(fetch_url)

    try:
        r = requests.get(fetch_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"    Deel error ({fetch_url}): {e}")
        return []

    return _parse_deel_jobs(r.text, slug, relevant_only=relevant_only)


def _parse_join_next_data(html: str) -> tuple[str | None, int | None, list[dict]]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None, None, []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, None, []
    state = data.get("props", {}).get("pageProps", {}).get("initialState", {})
    company = state.get("company") or {}
    jobs_block = state.get("jobs") or {}
    return (
        company.get("domain"),
        company.get("id"),
        list(jobs_block.get("items") or []),
    )


def _join_jobs_from_items(
    items: list[dict],
    slug: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    base = f"https://join.com/companies/{slug}"
    jobs: list[dict] = []
    seen: set[str] = set()
    for item in items:
        title = (item.get("title") or "").strip()
        id_param = (item.get("idParam") or "").strip()
        if not title or not id_param:
            continue
        if relevant_only and not is_relevant(title):
            continue
        url = f"{base}/{id_param}"
        if url in seen:
            continue
        seen.add(url)
        jobs.append({"title": title, "url": url})
    return jobs


def _fetch_join_items_via_api(
    company_id: int,
    *,
    headers: dict | None = None,
) -> list[dict]:
    hdrs = headers or HEADERS
    items: list[dict] = []
    page = 1
    while page <= 20:
        try:
            r = requests.get(
                f"https://join.com/api/public/companies/{company_id}/jobs",
                headers={**hdrs, "Accept": "application/json"},
                params={"page": page, "pageSize": 100},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        batch = list(data.get("items") or [])
        if not batch:
            break
        items.extend(batch)
        pagination = data.get("pagination") or {}
        page_count = int(pagination.get("pageCount") or 1)
        if page >= page_count:
            break
        page += 1
    return items


def scrape_join(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Scrape join.com company boards via __NEXT_DATA__ and public jobs API."""
    detected = _detect_join_from_url(careers_url)
    if not detected[1]:
        return []
    board_url = detected[1]
    slug_m = re.search(r"join\.com/companies/([a-zA-Z0-9_-]+)", board_url, re.I)
    slug = slug_m.group(1) if slug_m else board_url.rstrip("/").split("/")[-1]

    try:
        r = requests.get(board_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    Join error ({board_url}): {e}")
        return []

    slug_from_page, company_id, items = _parse_join_next_data(r.text)
    if slug_from_page:
        slug = slug_from_page

    if company_id:
        api_items = _fetch_join_items_via_api(company_id)
        if api_items:
            items = api_items

    return _join_jobs_from_items(items, slug, relevant_only=relevant_only)


# ── ATS REST API scrapers ─────────────────────────────────────────────────────

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


def scrape_personio(ats_url: str, *, relevant_only: bool = True) -> list[dict]:
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
                cleaned = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', r.text)
                root = ElementTree.fromstring(cleaned.encode())
                positions = root.findall("position")
            jobs = []
            for pos in positions:
                title = pos.findtext("name") or ""
                job_id = pos.findtext("id") or ""
                office = (pos.findtext("office") or "").strip()
                if job_id and (not relevant_only or is_relevant(title)):
                    jobs.append(_listing_job(
                        title,
                        f"{base}/job/{job_id}",
                        location=office or None,
                    ))
            if jobs:
                return jobs
    except Exception as e:
        print(f"    Personio XML error ({ats_url}): {e}")

    jobs = scrape_personio_html(base, relevant_only=relevant_only)
    if jobs:
        print(f"    Personio XML unavailable, parsed {len(jobs)} job(s) from HTML")
    return jobs


def scrape_lever(ats_url: str) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1]
    is_eu = "eu.lever" in ats_url
    api_host = "jobs.eu.lever.co" if is_eu else "api.lever.co"
    api = f"https://{api_host}/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return [
            _listing_job(
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


def scrape_greenhouse(ats_url: str) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
    if not slug or slug in ("embed", "jobs", ""):
        return []
    api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return [
            _listing_job(
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



def _bol_doelgroep_from_url(careers_url: str) -> str | None:
    qs = parse_qs(urlparse(careers_url).query)
    vals = qs.get("doelgroep[]") or qs.get("doelgroep")
    return vals[0] if vals else None


def _bol_search_payload(careers_url: str, *, size: int = 200) -> dict:
    doelgroep = _bol_doelgroep_from_url(careers_url)
    if doelgroep:
        es_query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_all": {}},
                        {
                            "bool": {
                                "should": [
                                    {"bool": {"filter": [{"term": {"doelgroep": doelgroep}}]}}
                                ]
                            }
                        },
                    ]
                }
            },
            "sort": [{"_score": "desc"}],
            "from": 0,
            "size": size,
        }
    else:
        es_query = {
            "query": {"bool": {"must": [{"match_all": {}}]}},
            "sort": [{"_score": "desc"}],
            "from": 0,
            "size": size,
        }
    return {
        "body": json.dumps(es_query),
        "languages": ["nl", "en"],
        "preferred_language": "en",
    }


def _jobs_from_bol_response(data: dict) -> list[dict]:
    hits = (data.get("results") or {}).get("hits", {}).get("hits", [])
    jobs: list[dict] = []
    for hit in hits:
        src = hit.get("_source") or {}
        title = (src.get("publicatienaam") or src.get("post_title") or "").strip()
        if not title:
            continue
        slug = (src.get("slug") or "").strip()
        if slug.startswith("/"):
            job_url = urljoin("https://careers.bol.com", slug)
        elif slug:
            job_url = slug
        else:
            job_url = "https://careers.bol.com/en/jobs/"
        jobs.append({"title": title, "url": job_url})
    return jobs


JOB_SHOP_TYPESENSE_URL = "https://api.my-job-shop.com/api/typesense/multi_search"




def _job_shop_search_payload(
    tenant_id: str,
    vanity: str,
    *,
    page: int = 1,
    per_page: int = 100,
) -> dict:
    return {
        "searches": [{
            "collection": "offers",
            "q": "*",
            "query_by": "title",
            "per_page": per_page,
            "page": page,
            "filter_by": (
                f"tenant_id:={tenant_id}&&backoffice_vanity:={vanity}&&status:=ACTIVE"
            ),
        }],
    }


def _jobs_from_job_shop_response(data: dict, *, relevant_only: bool = True) -> list[dict]:
    jobs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for result in data.get("results", []):
        for hit in result.get("hits", []):
            doc = hit.get("document") or hit
            title = (doc.get("title") or "").strip()
            url = (doc.get("url") or "").strip()
            if not title or not url:
                continue
            if relevant_only and not is_relevant(title):
                continue
            key = (title.casefold(), url)
            if key in seen:
                continue
            seen.add(key)
            jobs.append({"title": title, "url": url})
    return jobs


def scrape_job_shop(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Talents Connect / Job Shop boards (api.my-job-shop.com + Typesense)."""
    page_url = (careers_url or "").split("#", 1)[0].strip() or careers_url
    if not page_url:
        return []
    if "/search" not in page_url:
        page_url = page_url.rstrip("/") + "/search"

    try:
        r = requests.get(page_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return []

    config = _parse_job_shop_config(r.text, careers_url)
    if not config:
        print(f"    Job Shop error ({careers_url}): could not parse board config")
        return []

    api_key, tenant_id, vanity = config
    headers = {
        **HEADERS,
        "X-TYPESENSE-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    jobs: list[dict] = []
    page = 1
    per_page = 100
    total = None
    try:
        while True:
            r = requests.post(
                JOB_SHOP_TYPESENSE_URL,
                json=_job_shop_search_payload(
                    tenant_id, vanity, page=page, per_page=per_page
                ),
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            result = (data.get("results") or [{}])[0]
            if total is None:
                total = int(result.get("found") or 0)
            batch = _jobs_from_job_shop_response(
                {"results": [result]},
                relevant_only=relevant_only,
            )
            jobs.extend(batch)
            if page * per_page >= total or not result.get("hits"):
                break
            page += 1
        return jobs
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return jobs


def scrape_bol(careers_url: str) -> list[dict]:
    """bol careers.bol.com uses a custom WP/Elasticsearch API, not boards.greenhouse.io."""
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": careers_url or "https://careers.bol.com/en/jobs/",
    }
    try:
        r = requests.post(
            BOL_CAREERS_API,
            json=_bol_search_payload(careers_url),
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            print(f"    bol careers API error: {data}")
            return []
        return _jobs_from_bol_response(data)
    except Exception as e:
        print(f"    bol careers error ({careers_url}): {e}")
        return []


def scrape_ashby(ats_url: str) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1]
    api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        jobs = r.json().get("jobs", []) or []
        return [
            _listing_job(
                j["title"],
                j.get("jobUrl", ats_url),
                location=j.get("location") or j.get("locationName"),
            )
            for j in jobs
            if is_relevant(j.get("title", ""))
        ]
    except Exception as e:
        print(f"    Ashby API error ({ats_url}): {e}")
        # Playwright fallback for Ashby embed pages
        return scrape_with_playwright(ats_url)


def _workable_slug_from_url(ats_url: str) -> str:
    m = re.search(r"apply\.workable\.com/(?:api/v\d+/accounts/)?([a-z0-9-]+)", ats_url, re.I)
    if m and m.group(1).lower() != "api":
        return m.group(1)
    return ""


def scrape_workable(ats_url: str) -> list[dict]:
    slug = _workable_slug_from_url(ats_url)
    if not slug:
        print(f"    Workable error ({ats_url}): missing account slug")
        return []
    api = f"https://apply.workable.com/api/v2/accounts/{slug}/jobs"
    try:
        r = requests.post(
            api,
            json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
            headers=HEADERS, timeout=10,
        )
        r.raise_for_status()
        return [
            _listing_job(
                j["title"],
                f"https://apply.workable.com/{slug}/j/{j['shortcode']}/",
                location=_workable_location_text(j.get("location")),
            )
            for j in r.json().get("results", [])
            if is_relevant(j.get("title", ""))
        ]
    except Exception as e:
        print(f"    Workable error ({ats_url}): {e}")
        return []


def scrape_recruitee(ats_url: str) -> list[dict]:
    parsed = urlparse(ats_url)
    slug = parsed.netloc.split(".")[0]
    api = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = requests.get(api, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return [
            _listing_job(
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


def scrape_smartrecruiters(ats_url: str) -> list[dict]:
    company_id = _smartrecruiters_company_id(ats_url)
    if not company_id:
        print(f"    SmartRecruiters error ({ats_url}): could not parse company id")
        return []
    jobs: list[dict] = []
    offset = 0
    try:
        while True:
            api = (
                f"{_smartrecruiters_api_url(company_id)}"
                f"?limit=100&offset={offset}&include=locations"
            )
            r = requests.get(api, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            content = data.get("content") or []
            for j in content:
                title = j.get("name") or ""
                if is_relevant(title):
                    jobs.append(_listing_job(
                        title,
                        f"https://jobs.smartrecruiters.com/{company_id}/{j['id']}",
                        location=_smartrecruiters_location_text(j.get("location")),
                    ))
            offset += len(content)
            total = data.get("totalFound", offset)
            if not content or offset >= total:
                break
        return jobs
    except Exception as e:
        print(f"    SmartRecruiters error ({ats_url}): {e}")
        return []


def _teamtailor_board_url(api_key_or_url: str, careers_url: str) -> str:
    if (api_key_or_url or "").startswith("http"):
        return api_key_or_url.rstrip("/")
    board = (careers_url or "").rstrip("/")
    if ".teamtailor.com" in board and not board.endswith("/jobs"):
        return f"{board.split('?')[0]}/jobs" if "/jobs" not in board else board.split("?")[0]
    return board


def _scrape_teamtailor_html_board(
    board_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    """TeamTailor career sites paginate with ?page=2 — not a real job posting."""
    board = _teamtailor_board_url(board_url, board_url)
    if not board.endswith("/jobs"):
        board = f"{board.rstrip('/')}/jobs"

    merged: dict[str, str] = {}
    page = 1
    while page <= 25:
        page_url = board if page == 1 else f"{board}?page={page}"
        if page > 1:
            _report_activity(f"Loading TeamTailor page {page}…")
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            if page == 1:
                print(f"    TeamTailor HTML error ({page_url}): {e}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        batch = _collect_listing_job_links(soup, board)
        new_urls = [u for u in batch if u not in merged]
        if not new_urls:
            break
        for url in new_urls:
            merged[url] = batch[url]
        page += 1

    if not merged:
        return []
    jobs = _listing_candidates_to_jobs(merged, relevant_only=relevant_only)
    if jobs:
        print(f"    TeamTailor HTML board: {len(jobs)} role(s) across {page - 1} page(s)")
    return jobs


def _teamtailor_location_map(included: list[dict] | None) -> dict[str, str]:
    loc_by_id: dict[str, str] = {}
    for item in included or []:
        if item.get("type") != "locations":
            continue
        attrs = item.get("attributes") or {}
        loc_by_id[item["id"]] = ", ".join(
            dict.fromkeys(
                p for p in (
                    (attrs.get("city") or "").strip(),
                    (attrs.get("country") or "").strip(),
                    (attrs.get("name") or "").strip(),
                ) if p
            )
        )
    return loc_by_id


def _teamtailor_listing_jobs_from_feed(
    jobs: list[dict],
    included: list[dict] | None,
    careers_url: str,
    *,
    relevant_only: bool,
) -> list[dict]:
    loc_by_id = _teamtailor_location_map(included)
    out: list[dict] = []
    for j in jobs:
        title = (j.get("attributes") or {}).get("title", "")
        if relevant_only and not is_relevant(title):
            continue
        loc_refs = (
            (j.get("relationships") or {}).get("locations") or {}
        ).get("data") or []
        locs = [
            loc_by_id[ref["id"]]
            for ref in loc_refs
            if ref.get("id") and loc_by_id.get(ref["id"])
        ]
        out.append(_listing_job(
            title,
            j.get("links", {}).get("careersite-job-url", careers_url),
            location=locs[0] if len(locs) == 1 else None,
            locations=locs or None,
        ))
    return out


def scrape_teamtailor(
    api_key_or_url: str,
    careers_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    """
    ats_url stores the API key when known, otherwise the board URL.
    Prefer the REST API; otherwise paginate the public HTML board.
    """
    key = api_key_or_url if api_key_or_url and not api_key_or_url.startswith("http") else ""
    board_url = _teamtailor_board_url(api_key_or_url, careers_url)

    if key:
        jobs, included = _fetch_teamtailor_jobs(key)
        if jobs:
            out = _teamtailor_listing_jobs_from_feed(
                jobs, included, careers_url, relevant_only=relevant_only,
            )
            if out:
                return out

    jobs = _scrape_teamtailor_html_board(board_url, relevant_only=relevant_only)
    if jobs:
        return jobs
    return scrape_with_playwright(careers_url)


def _fetch_teamtailor_jobs(api_key: str) -> tuple[list[dict], list[dict]]:
    """Teamtailor public job feed via Authorization token + pagination."""
    headers_base = {
        **HEADERS,
        "Authorization": f"Token token={api_key}",
        "Accept": "application/vnd.api+json",
    }
    for version in ("20240404", "20210218", "20161108"):
        jobs: list[dict] = []
        included: list[dict] = []
        url = (
            "https://api.teamtailor.com/v1/jobs"
            "?include=department,locations&page[size]=30&filter[feed]=public"
        )
        hdrs = {**headers_base, "X-Api-Version": version}
        try:
            while url:
                r = requests.get(url, headers=hdrs, timeout=15)
                if r.status_code == 406 and version != "20161108":
                    break
                r.raise_for_status()
                data = r.json()
                jobs.extend(data.get("data") or [])
                included.extend(data.get("included") or [])
                url = (data.get("links") or {}).get("next")
            if jobs:
                return jobs, included
        except Exception:
            continue

    # Legacy query-param auth used by some older embeds.
    try:
        r = requests.get(
            f"https://api.teamtailor.com/v1/jobs?api_key={api_key}&page[size]=30&filter[feed]=public",
            headers={**HEADERS, "X-Api-Version": "20210218"},
            timeout=15,
        )
        if r.ok:
            data = r.json()
            return list(data.get("data") or []), list(data.get("included") or [])
    except Exception:
        pass
    return [], []


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
        location = _bamboohr_location_text(item) or None
        jobs.append(_listing_job(title, f"{base}/{job_id}", location=location))
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


def scrape_workday(ats_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Workday CXS API (myworkdayjobs.com / myworkdaysite.com)."""
    api, base = _workday_api_and_base(ats_url)
    if not api or not base:
        print(f"    Workday error ({ats_url}): missing API/base config")
        return []
    jobs: list[dict] = []
    offset = 0
    limit = 20
    total: int | None = None
    while offset <= 2000:
        try:
            r = requests.post(
                api,
                json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=25,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    Workday error ({api}): {e}")
            break
        postings = data.get("jobPostings") or []
        if total is None:
            total = int(data.get("total") or len(postings))
        for posting in postings:
            path = posting.get("externalPath") or ""
            title = posting.get("title") or ""
            if not path or not title:
                continue
            job_url = base.rstrip("/") + path
            if relevant_only and not is_relevant(title):
                continue
            jobs.append(_listing_job(
                title,
                job_url,
                location=(posting.get("locationsText") or posting.get("location") or "").strip()
                or None,
            ))
        offset += limit
        if not postings or offset >= total:
            break
    if jobs:
        print(f"    Workday: {len(jobs)} role(s) from {total or '?'} posting(s)")
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




def scrape_jibe(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Booking.com / Jibe Angular job search (requires Playwright)."""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    merged: dict[str, str] = {}
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as p:
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


def scrape_atlassian(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Atlassian native careers board (JS-rendered detail links)."""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    merged: dict[str, str] = {}
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as p:
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


def scrape_with_playwright(
    page_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    """Render JS-heavy pages with Playwright and extract job links from DOM."""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as p:
                browser, context = _playwright_browser_context(p)
                page = context.new_page()
                page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
                _playwright_pause(page, 3500)
                raise_if_cancelled()
                html = page.content()
                browser.close()

        return _jobs_from_listing_html(html, page_url, relevant_only=relevant_only)
    except FetchCancelled:
        raise
    except Exception as e:
        print(f"    Playwright error ({page_url}): {e}")
        return []


# ── Visa / relocation detection from job descriptions ────────────────────────

# Patterns aligned with relocate.me relocation-package guide:
# https://relocate.me/international-jobs/job-search-guide/relocation-packages
# Basic: visa sponsorship + flight tickets. Advanced: housing, settling-in, allowance.
VISA_RELOCATION_POSITIVE = [
    r"visa\s+sponsor",
    r"visa\s+(?:application|paperwork|support|assistance)",
    r"sponsor(?:ing)?(?:\s+\w+){0,4}\s+visas?",
    r"provide\s+visa\s+sponsor",
    r"work\s+permit\s+sponsor",
    r"immigration\s+(?:support|sponsor|assistance)",
    r"relocation\s+(?:support|package|packages|compensation|assistance|benefit|allowance|help|bonus|stipend|aid)",
    r"relocation\s+allowance",
    r"help\s+you\s+relocate",
    r"relocate\s+(?:to|you|candidates|international)",
    r"relocation\s+to\s+(?:the\s+)?\w+",
    r"provide\s+relocation",
    r"offer\s+relocation",
    r"(?:flight|airfare|air\s+fare|travel)\s+(?:ticket|cost|expense|reimbursement)",
    r"(?:temporary|short[- ]term)\s+(?:housing|accommodation|rental)",
    r"(?:accommodation|housing)\s+assistance",
    r"settling[- ]in\s+(?:support|assistance|services?)",
    r"moving\s+expenses?",
    r"sign[- ]on\s+bonus.*relocat",
    r"relocat.*sign[- ]on\s+bonus",
    r"welcome\s+applications\s+from\s+(?:talent\s+)?worldwide",
    r"international\s+(?:candidates|applicants|talent)",
]

VISA_RELOCATION_NEGATIVE = [
    r"(?:no|not|cannot|can't|unable\s+to|do\s+not|don't|does\s+not|won't|will\s+not)\s+(?:\w+\s+){0,4}(?:offer\s+)?(?:visa\s+)?sponsor",
    r"(?:no|not)\s+relocation",
    r"without\s+(?:visa\s+)?sponsor",
    r"un(?:able|fortunatel\w+)\s+to\s+(?:offer\s+)?sponsor",
    r"not\s+(?:currently\s+)?(?:able\s+to\s+)?sponsor",
    r"must\s+(?:already\s+)?(?:have|possess)\s+(?:existing\s+)?(?:the\s+)?(?:legal\s+)?right\s+to\s+work",
    r"(?:only\s+)?(?:open\s+to|candidates\s+with)\s+(?:existing\s+)?right\s+to\s+work",
    r"must\s+be\s+(?:legally\s+)?(?:eligible|authorized)\s+to\s+work",
]


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split()).lower()


def detect_visa_relocation(text: str) -> bool | None:
    """Return True/False for visa or relocation support; None if text unavailable."""
    if not text:
        return None
    normalized = text.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    if any(re.search(p, normalized) for p in VISA_RELOCATION_POSITIVE):
        return True
    if any(re.search(p, normalized) for p in VISA_RELOCATION_NEGATIVE):
        return False
    return False


def _fetch_greenhouse_job_text(url: str) -> str:
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
                return _html_to_text(r.json()["content"])
        except Exception:
            pass
    return ""


def _fetch_lever_job_text(url: str) -> str:
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
        return _html_to_text("\n".join(parts))
    except Exception:
        return ""


def _fetch_recruitee_job_text(url: str) -> str:
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
                    return _html_to_text(desc)
    except Exception:
        pass
    return ""


def _fetch_ashby_job_text(url: str) -> str:
    m = re.search(r"ashbyhq\.com/[^/]+/([0-9a-f-]{36})", url, re.I)
    if not m:
        return ""
    org_m = re.search(r"ashbyhq\.com/([^/]+)/", url, re.I)
    org = org_m.group(1) if org_m else ""
    if org:
        api = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensationRanges=true"
        try:
            r = requests.get(api, headers=HEADERS, timeout=10)
            if r.ok:
                for job in r.json().get("jobs", []) or []:
                    if job.get("id") == m.group(1) or m.group(1) in (job.get("jobUrl") or ""):
                        return _html_to_text(job.get("descriptionHtml") or job.get("description") or "")
        except Exception:
            pass
    return ""


def fetch_job_description(url: str, ats_type: str | None = None) -> str:
    """Fetch plain-text job description for visa/relocation checks."""
    fetchers = {
        "greenhouse": _fetch_greenhouse_job_text,
        "greenhouse_eu": _fetch_greenhouse_job_text,
        "lever": _fetch_lever_job_text,
        "lever_eu": _fetch_lever_job_text,
        "recruitee": _fetch_recruitee_job_text,
        "ashby": _fetch_ashby_job_text,
    }
    if ats_type in fetchers:
        text = fetchers[ats_type](url)
        if text:
            return text

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.ok:
            text = _html_to_text(r.text)
            if len(text) > 200:
                return text
    except Exception:
        pass

    if PLAYWRIGHT_AVAILABLE:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(2500)
                text = _html_to_text(page.content())
                browser.close()
                return text
        except Exception:
            pass
    return ""


def _normalize_job_url(url: str) -> str:
    """Backward-compatible alias — prefer job_identity.normalize_job_url."""
    from relocation_jobs.core.job_identity import normalize_job_url
    return normalize_job_url(url)


def merge_matching_jobs(
    existing: list[dict],
    scraped: list[dict],
) -> tuple[list[dict], int, int, int]:
    """
    Merge a fresh scrape into the cached job list keyed by URL idempotency.

    - Same idempotency key: keep original ``fetched`` and ``last_seen``,
      refresh title/visa from scrape when missing.
    - New key: add job with ``fetched`` and ``last_seen`` set to now.
    - Missing from this scrape: keep all cached roles (fetch adds, never removes).

    Returns (merged, preserved_count, new_count, stale_kept_count).
    """
    seen_at = now_iso()
    by_key: dict[str, dict] = {}
    for job in existing:
        key = job_idempotency_key_for_job(job)
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = job
            continue
        # Duplicate rows in cache — keep the one with the earliest fetched date.
        prev_fetched = prev.get("fetched") or "9999-99-99"
        job_fetched = job.get("fetched") or "9999-99-99"
        if job_fetched < prev_fetched:
            by_key[key] = job

    merged: list[dict] = []
    seen: set[str] = set()
    preserved = 0
    new_count = 0

    for job in scraped:
        key = job_idempotency_key(job.get("url", ""))
        if not key or key in seen:
            continue
        seen.add(key)

        if key in by_key:
            old = by_key[key]
            merged_job: dict = {
                "title": job.get("title") or old.get("title", ""),
                "url": old.get("url") or job.get("url", ""),
                "idempotency_key": key,
            }
            # First-seen and last-seen — never bump on re-scrape of same role.
            if old.get("fetched"):
                merged_job["fetched"] = old["fetched"]
            elif job.get("fetched"):
                merged_job["fetched"] = job["fetched"]
            else:
                merged_job["fetched"] = seen_at
            if old.get("last_seen"):
                merged_job["last_seen"] = old["last_seen"]
            elif old.get("fetched"):
                merged_job["last_seen"] = old["fetched"]
            elif job.get("last_seen"):
                merged_job["last_seen"] = job["last_seen"]
            else:
                merged_job["last_seen"] = merged_job["fetched"]

            if old.get("visa_sponsorship") is not None:
                merged_job["visa_sponsorship"] = old["visa_sponsorship"]
            elif job.get("visa_sponsorship") is not None:
                merged_job["visa_sponsorship"] = job["visa_sponsorship"]

            if old.get("applied"):
                merged_job["applied"] = True
                if old.get("applied_date"):
                    merged_job["applied_date"] = old["applied_date"]

            if old.get("not_for_me"):
                merged_job["not_for_me"] = True
                if old.get("not_for_me_date"):
                    merged_job["not_for_me_date"] = old["not_for_me_date"]

            if old.get("rejected"):
                merged_job["rejected"] = True
                if old.get("rejected_date"):
                    merged_job["rejected_date"] = old["rejected_date"]

            _copy_listing_location_fields(merged_job, job, old)

            merged.append(merged_job)
            preserved += 1
        else:
            merged_job = dict(job)
            merged_job["idempotency_key"] = key
            merged_job["fetched"] = merged_job.get("fetched") or seen_at
            merged_job["last_seen"] = seen_at
            merged.append(merged_job)
            new_count += 1

    stale_kept = 0
    for key, old in by_key.items():
        if key not in seen:
            kept = dict(old)
            stamp_job_identity(kept)
            merged.append(kept)
            stale_kept += 1

    for job in merged:
        stamp_job_identity(job)

    return merged, preserved, new_count, stale_kept


def _copy_listing_location_fields(target: dict, *sources: dict) -> None:
    """Preserve listing location metadata from scrape or cache."""
    location = ""
    locations = None
    for source in sources:
        if not location:
            location = (source.get("location") or "").strip()
        if locations is None and source.get("locations"):
            locations = source.get("locations")
    if location:
        target["location"] = location
    if locations:
        target["locations"] = locations


def backfill_listing_locations(jobs: list[dict], scrape_sources: list[dict]) -> None:
    """Copy listing location from the latest scrape onto cached roles.

    Roles kept from cache (including those filtered out by the location gate) still
    receive ``location`` / ``locations`` when the ATS board lists them.
    """
    by_key: dict[str, dict] = {}
    for source in scrape_sources:
        key = job_idempotency_key(source.get("url", ""))
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = source
            continue
        if (source.get("location") or source.get("locations")) and not (
            prev.get("location") or prev.get("locations")
        ):
            by_key[key] = source

    for job in jobs:
        source = by_key.get(job_idempotency_key_for_job(job))
        if source:
            _copy_listing_location_fields(job, source)


def _enrich_one_job(
    job: dict,
    ats_type: str | None,
    fetched: str,
    only_missing: bool,
    *,
    preserve_fetched: bool = False,
) -> None:
    if preserve_fetched and job.get("fetched"):
        if only_missing and job.get("visa_sponsorship") is not None:
            return
        if only_missing:
            return
    elif only_missing and job.get("visa_sponsorship") is not None:
        if not preserve_fetched:
            job["fetched"] = fetched
        return
    text = fetch_job_description(job["url"], ats_type)
    job["visa_sponsorship"] = detect_visa_relocation(text)
    if not preserve_fetched or not job.get("fetched"):
        job["fetched"] = fetched


def enrich_jobs(
    jobs: list[dict],
    company: dict,
    only_missing: bool = False,
    *,
    workers: int = 4,
) -> list[dict]:
    """Sync wrapper — runs async enrichment on the event loop."""
    if not jobs:
        return jobs
    if not HTTPX_AVAILABLE:
        for job in jobs:
            _enrich_one_job(
                job, company.get("ats_type"), today(), only_missing,
                preserve_fetched=True,
            )
        return jobs

    async def _run() -> list[dict]:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=httpx.Timeout(15.0), follow_redirects=True
        ) as client:
            return await enrich_jobs_async_with_client(
                client, jobs, company,
                only_missing=only_missing,
                concurrency=workers,
                preserve_fetched=False,
            )

    return asyncio.run(_run())


async def fetch_job_description_async(
    client: httpx.AsyncClient,
    url: str,
    ats_type: str | None = None,
) -> str:
    """Visa check text fetch — ATS helpers stay sync; generic page uses async HTTP."""
    if ats_type in ("greenhouse", "greenhouse_eu", "lever", "lever_eu", "recruitee", "ashby"):
        return await asyncio.to_thread(fetch_job_description, url, ats_type)
    try:
        r = await client.get(url, timeout=15.0)
        if r.is_success:
            text = _html_to_text(r.text)
            if len(text) > 200:
                return text
    except Exception:
        pass
    if PLAYWRIGHT_AVAILABLE:
        return await asyncio.to_thread(fetch_job_description, url, ats_type)
    return ""


async def _enrich_one_job_async(
    client: httpx.AsyncClient,
    job: dict,
    ats_type: str | None,
    fetched: str,
    only_missing: bool,
    *,
    preserve_fetched: bool = False,
) -> None:
    if preserve_fetched and job.get("fetched"):
        if only_missing and job.get("visa_sponsorship") is not None:
            return
        if only_missing:
            return
    elif only_missing and job.get("visa_sponsorship") is not None:
        if not preserve_fetched:
            job["fetched"] = fetched
        return
    text = await fetch_job_description_async(client, job["url"], ats_type)
    job["visa_sponsorship"] = detect_visa_relocation(text)
    if not preserve_fetched or not job.get("fetched"):
        job["fetched"] = fetched


async def enrich_jobs_async_with_client(
    client: httpx.AsyncClient,
    jobs: list[dict],
    company: dict,
    only_missing: bool = False,
    *,
    concurrency: int = 8,
    preserve_fetched: bool = False,
) -> list[dict]:
    if not jobs:
        return jobs
    ats_type = company.get("ats_type")
    fetched = today()
    sem = asyncio.Semaphore(max(1, min(concurrency, len(jobs))))

    async def one(job: dict) -> None:
        raise_if_cancelled()
        async with sem:
            raise_if_cancelled()
            await _enrich_one_job_async(
                client, job, ats_type, fetched, only_missing,
                preserve_fetched=preserve_fetched,
            )

    try:
        await asyncio.gather(*(one(j) for j in jobs))
    except FetchCancelled:
        pass
    return jobs


def scrape_generic(url: str) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    Fetch error: {e}")
        return []

    return _jobs_from_listing_html(r.text, url)


# ── Core dispatch: detect ATS → call scraper ─────────────────────────────────


def _apply_known_ats_override(company: dict, save_fn=None) -> None:
    """Use KNOWN_ATS or join.com URL when cache is empty or wrongly set to generic."""
    name = company.get("name", "")
    cached = (company.get("ats_type") or "").strip()
    careers_url = company.get("careers_url") or ""

    if name in KNOWN_ATS:
        if not cached or cached == "generic" or name in FORCE_KNOWN_ATS:
            known_type, known_url = KNOWN_ATS[name]
            company["ats_type"] = known_type
            company["ats_url"] = known_url
            print(f"    Known override: {known_type} → {known_url}")
            if save_fn:
                save_fn()
        return

    sr = _detect_smartrecruiters_from_careers_url(careers_url)
    if sr[0]:
        cached_id = _smartrecruiters_company_id(company.get("ats_url") or "")
        expected_id = _smartrecruiters_company_id(sr[1])
        if cached != "smartrecruiters" or cached_id != expected_id:
            company["ats_type"] = sr[0]
            company["ats_url"] = sr[1]
            print(f"    SmartRecruiters careers URL: {sr[1]}")
            if save_fn:
                save_fn()
            return

    if careers_url and (not cached or cached == "generic"):
        detectors = (
            ("SmartRecruiters", _detect_smartrecruiters_from_careers_url),
            ("JobShop", _detect_job_shop_from_url),
            ("Deel", _detect_deel_from_url),
            ("Join", _detect_join_from_url),
            ("ApplyToJob", _detect_applytojob_from_url),
            ("BambooHR", _detect_bamboohr_from_url),
            ("Recruitee", _detect_recruitee_from_careers_host),
            ("SmartRecruiters", _detect_smartrecruiters_from_redcare_careers),
        )
        for label, detector in detectors:
            ats_type, ats_url = detector(careers_url)
            if ats_type:
                company["ats_type"] = ats_type
                company["ats_url"] = ats_url
                print(f"    {label} careers URL: {ats_url}")
                if save_fn:
                    save_fn()
                break


def _effective_cached_ats(company: dict) -> tuple[str | None, str]:
    """Treat persisted ``generic`` as unknown — it is wrong too often."""
    cached = (company.get("ats_type") or "").strip()
    if cached == "generic":
        return None, ""
    if cached:
        return cached, company.get("ats_url") or ""
    return None, ""


def _persist_detected_ats(
    company: dict,
    ats_type: str | None,
    ats_url: str,
    save_fn=None,
) -> str:
    """Persist a concrete ATS type; use generic scraper at runtime only when unknown."""
    if ats_type:
        company["ats_type"] = ats_type
        company["ats_url"] = ats_url or ""
    else:
        company["ats_type"] = ""
        company["ats_url"] = ""
    if save_fn:
        save_fn()
    return ats_type or "generic"


def get_jobs(company: dict, save_fn=None) -> list[dict]:
    """
    Detect or use cached ATS, scrape jobs, and return list.
    If save_fn is provided it's called after ATS detection to persist cache.
    """
    name = company["name"]
    careers_url = company.get("careers_url")
    if not careers_url:
        return []

    _apply_known_ats_override(company, save_fn)

    ats_type, ats_url = _effective_cached_ats(company)

    # ── 1. Auto-detect if not cached ─────────────────────────────────────────
    if not ats_type:
        # Check known corrections first (companies with non-detectable setups)
        if name in KNOWN_ATS:
            ats_type, ats_url = KNOWN_ATS[name]
            print(f"    Known: {ats_type} → {ats_url}")
        else:
            # Try fast static HTML detection first
            ats_type, ats_url = detect_ats_static(careers_url)

            # If static failed, use Playwright XHR interception
            if not ats_type:
                print(f"    Detecting ATS via Playwright...")
                ats_type, ats_url = detect_ats_via_playwright(careers_url)

            if ats_type:
                print(f"    Detected: {ats_type} → {ats_url}")
            else:
                print(f"    No ATS detected, using generic Playwright scraper")

        # Validate detected result — fall back to KNOWN_ATS if slug looks wrong
        if ats_type and ats_url:
            slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
            is_proxy = "careers-analytics" in ats_url
            is_bad_slug = slug in ("embed", "jobs", "")
            if (is_bad_slug or is_proxy) and name in KNOWN_ATS:
                print(f"    Bad detection (slug='{slug}'), using known correction")
                ats_type, ats_url = KNOWN_ATS[name]

        ats_type = _persist_detected_ats(company, ats_type, ats_url, save_fn)
        ats_url = company.get("ats_url") or ats_url

    # ── 2. Dispatch to correct scraper ───────────────────────────────────────
    effective_url = ats_url or careers_url

    if ats_type == "personio":
        return scrape_personio(effective_url)
    elif ats_type in ("lever", "lever_eu"):
        return scrape_lever(effective_url)
    elif ats_type in ("greenhouse", "greenhouse_eu"):
        return scrape_greenhouse(effective_url)
    elif ats_type == "bol":
        return scrape_bol(careers_url)
    elif ats_type == "job_shop":
        return scrape_job_shop(effective_url or careers_url)
    elif ats_type == "ashby":
        return scrape_ashby(effective_url)
    elif ats_type == "workable":
        return scrape_workable(effective_url)
    elif ats_type == "recruitee":
        return scrape_recruitee(effective_url)
    elif ats_type == "smartrecruiters":
        return scrape_smartrecruiters(effective_url)
    elif ats_type == "teamtailor":
        return scrape_teamtailor(effective_url, careers_url)
    elif ats_type == "join":
        return scrape_join(effective_url or careers_url)
    elif ats_type == "deel":
        return scrape_deel(effective_url or careers_url)
    elif ats_type == "applytojob":
        return scrape_applytojob(effective_url or careers_url)
    elif ats_type == "bamboohr":
        return scrape_bamboohr(effective_url or careers_url)
    elif ats_type == "movingimage":
        return scrape_movingimage(effective_url or careers_url)
    elif ats_type == "project_a":
        return scrape_project_a(effective_url or careers_url)
    elif ats_type == "workday":
        return scrape_workday(effective_url)
    elif ats_type == "hirehive":
        return scrape_hirehive(effective_url)
    elif ats_type == "epam":
        return scrape_epam(effective_url)
    elif ats_type == "rss":
        return scrape_rss(effective_url)
    elif ats_type == "jibe":
        return scrape_jibe(effective_url or careers_url)
    elif ats_type == "atlassian":
        return scrape_atlassian(effective_url or careers_url)
    else:
        # generic: try static HTML first, then Playwright
        jobs = scrape_generic(careers_url)
        if not jobs and PLAYWRIGHT_AVAILABLE:
            jobs = scrape_with_playwright(careers_url)
        return jobs


# ── Async I/O (httpx + asyncio event loop) ───────────────────────────────────

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
    slug = _deel_slug_from_url(fetch_url)

    try:
        r = await client.get(fetch_url, timeout=20.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Deel error ({fetch_url}): {e}")
        return []

    return _parse_deel_jobs(r.text, slug, relevant_only=relevant_only)




async def scrape_lever_async(client: httpx.AsyncClient, ats_url: str) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1]
    is_eu = "eu.lever" in ats_url
    api_host = "jobs.eu.lever.co" if is_eu else "api.lever.co"
    api = f"https://{api_host}/v0/postings/{slug}?mode=json"
    try:
        r = await client.get(api, timeout=10.0)
        r.raise_for_status()
        return [
            _listing_job(
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
            _listing_job(
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


async def scrape_job_shop_async(
    client: httpx.AsyncClient,
    careers_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    page_url = (careers_url or "").split("#", 1)[0].strip() or careers_url
    if not page_url:
        return []
    if "/search" not in page_url:
        page_url = page_url.rstrip("/") + "/search"

    try:
        r = await client.get(page_url, timeout=20.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return []

    config = _parse_job_shop_config(r.text, careers_url)
    if not config:
        print(f"    Job Shop error ({careers_url}): could not parse board config")
        return []

    api_key, tenant_id, vanity = config
    headers = {
        **HEADERS,
        "X-TYPESENSE-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    jobs: list[dict] = []
    page = 1
    per_page = 100
    total = None
    try:
        while True:
            r = await client.post(
                JOB_SHOP_TYPESENSE_URL,
                json=_job_shop_search_payload(
                    tenant_id, vanity, page=page, per_page=per_page
                ),
                headers=headers,
                timeout=20.0,
            )
            r.raise_for_status()
            data = r.json()
            result = (data.get("results") or [{}])[0]
            if total is None:
                total = int(result.get("found") or 0)
            batch = _jobs_from_job_shop_response(
                {"results": [result]},
                relevant_only=relevant_only,
            )
            jobs.extend(batch)
            if page * per_page >= total or not result.get("hits"):
                break
            page += 1
        return jobs
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return jobs


async def scrape_bol_async(client: httpx.AsyncClient, careers_url: str) -> list[dict]:
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": careers_url or "https://careers.bol.com/en/jobs/",
    }
    try:
        r = await client.post(
            BOL_CAREERS_API,
            json=_bol_search_payload(careers_url),
            headers=headers,
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            print(f"    bol careers API error: {data}")
            return []
        return _jobs_from_bol_response(data)
    except Exception as e:
        print(f"    bol careers error ({careers_url}): {e}")
        return []


async def scrape_ashby_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    slug = ats_url.rstrip("/").split("/")[-1]
    api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = await client.get(api, timeout=10.0)
        r.raise_for_status()
        jobs = r.json().get("jobs", []) or []
        return [
            _listing_job(
                j["title"],
                j.get("jobUrl", ats_url),
                location=j.get("location") or j.get("locationName"),
            )
            for j in jobs
            if (j.get("title") or "").strip()
        ]
    except Exception as e:
        print(f"    Ashby API error ({ats_url}): {e}")
        return await asyncio.to_thread(
            scrape_with_playwright, ats_url, relevant_only=relevant_only
        )


async def scrape_workable_async(client: httpx.AsyncClient, ats_url: str) -> list[dict]:
    slug = _workable_slug_from_url(ats_url)
    if not slug:
        print(f"    Workable error ({ats_url}): missing account slug")
        return []
    api = f"https://apply.workable.com/api/v2/accounts/{slug}/jobs"
    try:
        r = await client.post(
            api,
            json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
            timeout=10.0,
        )
        r.raise_for_status()
        return [
            _listing_job(
                j["title"],
                f"https://apply.workable.com/{slug}/j/{j['shortcode']}/",
                location=_workable_location_text(j.get("location")),
            )
            for j in r.json().get("results", [])
            if (j.get("title") or "").strip()
        ]
    except Exception as e:
        print(f"    Workable error ({ats_url}): {e}")
        return []


async def scrape_recruitee_async(client: httpx.AsyncClient, ats_url: str) -> list[dict]:
    parsed = urlparse(ats_url)
    slug = parsed.netloc.split(".")[0]
    api = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = await client.get(api, timeout=10.0)
        r.raise_for_status()
        return [
            _listing_job(
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


async def scrape_smartrecruiters_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    company_id = _smartrecruiters_company_id(ats_url)
    if not company_id:
        print(f"    SmartRecruiters error ({ats_url}): could not parse company id")
        return []
    jobs: list[dict] = []
    offset = 0
    try:
        while True:
            api = (
                f"{_smartrecruiters_api_url(company_id)}"
                f"?limit=100&offset={offset}&include=locations"
            )
            r = await client.get(api, timeout=15.0)
            r.raise_for_status()
            data = r.json()
            content = data.get("content") or []
            for j in content:
                title = (j.get("name") or "").strip()
                if not title:
                    continue
                if relevant_only and not is_relevant(title):
                    continue
                jobs.append(_listing_job(
                    title,
                    f"https://jobs.smartrecruiters.com/{company_id}/{j['id']}",
                    location=_smartrecruiters_location_text(j.get("location")),
                ))
            offset += len(content)
            total = data.get("totalFound", offset)
            if not content or offset >= total:
                break
        return jobs
    except Exception as e:
        print(f"    SmartRecruiters error ({ats_url}): {e}")
        return []


async def scrape_workday_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    api, base = _workday_api_and_base(ats_url)
    if not api or not base:
        print(f"    Workday error ({ats_url}): missing API/base config")
        return []
    jobs: list[dict] = []
    offset = 0
    limit = 20
    total: int | None = None
    while offset <= 2000:
        try:
            r = await client.post(
                api,
                json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=25.0,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    Workday error ({api}): {e}")
            break
        postings = data.get("jobPostings") or []
        if total is None:
            total = int(data.get("total") or len(postings))
        for posting in postings:
            path = posting.get("externalPath") or ""
            title = posting.get("title") or ""
            if not path or not title:
                continue
            job_url = base.rstrip("/") + path
            if relevant_only and not is_relevant(title):
                continue
            jobs.append(_listing_job(
                title,
                job_url,
                location=(posting.get("locationsText") or posting.get("location") or "").strip()
                or None,
            ))
        offset += limit
        if not postings or offset >= total:
            break
    if jobs:
        print(f"    Workday: {len(jobs)} role(s) from {total or '?'} posting(s)")
    return jobs


async def scrape_hirehive_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    return await asyncio.to_thread(scrape_hirehive, ats_url, relevant_only=relevant_only)


async def scrape_epam_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    return await asyncio.to_thread(scrape_epam, ats_url, relevant_only=relevant_only)


async def scrape_rss_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    return await asyncio.to_thread(scrape_rss, ats_url, relevant_only=relevant_only)


async def scrape_personio_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    return await asyncio.to_thread(scrape_personio, ats_url, relevant_only=relevant_only)


async def scrape_join_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    detected = _detect_join_from_url(ats_url)
    if not detected[1]:
        return []
    board_url = detected[1]
    slug_m = re.search(r"join\.com/companies/([a-zA-Z0-9_-]+)", board_url, re.I)
    slug = slug_m.group(1) if slug_m else board_url.rstrip("/").split("/")[-1]

    try:
        r = await client.get(board_url, timeout=15.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Join error ({board_url}): {e}")
        return []

    slug_from_page, company_id, items = _parse_join_next_data(r.text)
    if slug_from_page:
        slug = slug_from_page

    if company_id:
        api_items: list[dict] = []
        page = 1
        while page <= 20:
            try:
                api_r = await client.get(
                    f"https://join.com/api/public/companies/{company_id}/jobs",
                    headers={"Accept": "application/json"},
                    params={"page": page, "pageSize": 100},
                    timeout=15.0,
                )
                api_r.raise_for_status()
                data = api_r.json()
            except Exception:
                break
            batch = list(data.get("items") or [])
            if not batch:
                break
            api_items.extend(batch)
            pagination = data.get("pagination") or {}
            page_count = int(pagination.get("pageCount") or 1)
            if page >= page_count:
                break
            page += 1
        if api_items:
            items = api_items

    return _join_jobs_from_items(items, slug, relevant_only=relevant_only)


async def scrape_generic_async(
    client: httpx.AsyncClient,
    url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    try:
        r = await client.get(url, timeout=15.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Fetch error: {e}")
        return []
    return await _jobs_from_listing_html_async(
        r.text, url, client, relevant_only=relevant_only
    )


async def get_jobs_async(
    client: httpx.AsyncClient,
    company: dict,
    save_fn=None,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    raise_if_cancelled()
    name = company["name"]
    careers_url = company.get("careers_url")
    if not careers_url:
        return []

    _apply_known_ats_override(company, save_fn)

    ats_type, ats_url = _effective_cached_ats(company)

    if not ats_type:
        if name in KNOWN_ATS:
            ats_type, ats_url = KNOWN_ATS[name]
            print(f"    Known: {ats_type} → {ats_url}")
        else:
            ats_type, ats_url = await detect_ats_static_async(client, careers_url)
            if not ats_type:
                raise_if_cancelled()
                print(f"    Detecting ATS via Playwright...")
                ats_type, ats_url = await asyncio.to_thread(
                    detect_ats_via_playwright, careers_url
                )
            if ats_type:
                print(f"    Detected: {ats_type} → {ats_url}")
            else:
                print(f"    No ATS detected, using generic Playwright scraper")

        if ats_type and ats_url:
            slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
            is_proxy = "careers-analytics" in ats_url
            is_bad_slug = slug in ("embed", "jobs", "")
            if (is_bad_slug or is_proxy) and name in KNOWN_ATS:
                print(f"    Bad detection (slug='{slug}'), using known correction")
                ats_type, ats_url = KNOWN_ATS[name]

        ats_type = _persist_detected_ats(company, ats_type, ats_url, save_fn)
        ats_url = company.get("ats_url") or ats_url

    effective_url = ats_url or careers_url
    raise_if_cancelled()

    runtime_ats = ats_type or "generic"
    _report_activity(
        f"Fetching roles via {runtime_ats}",
        detail=effective_url if effective_url != careers_url else careers_url,
    )

    if ats_type == "personio":
        jobs = await scrape_personio_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type in ("lever", "lever_eu"):
        jobs = await scrape_lever_async(client, effective_url)
    elif ats_type == "greenhouse_eu":
        jobs = await scrape_greenhouse_async(client, effective_url, eu=True)
    elif ats_type == "greenhouse":
        jobs = await scrape_greenhouse_async(client, effective_url, eu=False)
    elif ats_type == "bol":
        jobs = await scrape_bol_async(client, careers_url)
    elif ats_type == "job_shop":
        jobs = await scrape_job_shop_async(
            client, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "ashby":
        jobs = await scrape_ashby_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "workable":
        jobs = await scrape_workable_async(client, effective_url)
    elif ats_type == "recruitee":
        jobs = await scrape_recruitee_async(client, effective_url)
    elif ats_type == "smartrecruiters":
        jobs = await scrape_smartrecruiters_async(
            client, effective_url, relevant_only=relevant_only
        )
    elif ats_type == "teamtailor":
        jobs = await asyncio.to_thread(
            scrape_teamtailor, effective_url, careers_url, relevant_only=relevant_only
        )
    elif ats_type == "join":
        jobs = await scrape_join_async(
            client, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "deel":
        jobs = await scrape_deel_async(
            client, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "applytojob":
        jobs = await asyncio.to_thread(
            scrape_applytojob, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "bamboohr":
        jobs = await asyncio.to_thread(
            scrape_bamboohr, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "movingimage":
        jobs = await asyncio.to_thread(
            scrape_movingimage, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "project_a":
        jobs = await asyncio.to_thread(
            scrape_project_a, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "workday":
        jobs = await scrape_workday_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "hirehive":
        jobs = await scrape_hirehive_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "epam":
        jobs = await scrape_epam_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "rss":
        jobs = await scrape_rss_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "jibe":
        jobs = await asyncio.to_thread(
            scrape_jibe, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "atlassian":
        jobs = await asyncio.to_thread(
            scrape_atlassian, effective_url or careers_url, relevant_only=relevant_only
        )
    else:
        jobs = await scrape_generic_async(client, careers_url, relevant_only=relevant_only)
        if not jobs and PLAYWRIGHT_AVAILABLE:
            raise_if_cancelled()
            jobs = await asyncio.to_thread(
                scrape_with_playwright, careers_url, relevant_only=relevant_only
            )

    raise_if_cancelled()
    jobs = _filter_relevant_jobs(jobs, relevant_only)
    if relevant_only:
        _report_activity(f"Loaded {len(jobs)} matching role(s)")
    else:
        _report_activity(f"Loaded {len(jobs)} role(s) from careers page")
    return jobs


# ── Main ──────────────────────────────────────────────────────────────────────



def _emit_panel_ipc(kind: str, payload: dict) -> None:
    """Stdout markers consumed by panel_server when scraping in a subprocess."""
    if os.environ.get("PANEL_SCRAPE_CHILD"):
        print(f"@@{kind}@@{json.dumps(payload, separators=(',', ':'))}", flush=True)


def _report_activity(message: str, *, detail: str = "") -> None:
    message = (message or "").strip()
    if not message:
        return
    _emit_panel_ipc("ACTIVITY", {"message": message, "detail": (detail or "").strip()})




_progress_reporter: Callable[[dict], None] | None = None


def set_progress_reporter(reporter: Callable[[dict], None] | None) -> None:
    global _progress_reporter
    _progress_reporter = reporter


def clear_progress_reporter() -> None:
    set_progress_reporter(None)


_review_reporter: Callable[[dict], None] | None = None


def set_review_reporter(reporter: Callable[[dict], None] | None) -> None:
    global _review_reporter
    _review_reporter = reporter


def clear_review_reporter() -> None:
    set_review_reporter(None)


_JUNK_REVIEW_TITLE = re.compile(
    r"^(show\s+\d+\s+more|load\s+more|view\s+all(\s+jobs)?|see\s+all(\s+jobs)?)$",
    re.I,
)


def _review_entry(j: dict) -> dict | None:
    url = (j.get("url") or "").strip()
    if not url or _is_listing_noise_url(url):
        return None
    title = (j.get("title") or "").strip()
    if title and _JUNK_REVIEW_TITLE.match(title):
        return None
    entry = {"title": title or url, "url": url}
    reason = (j.get("filter_reason") or j.get("location_filter_reason") or "").strip()
    if reason:
        entry["filter_reason"] = reason
    return entry


def _review_filtered_jobs(
    all_scraped: list[dict],
    scraped: list[dict],
    company: dict,
    *,
    catalog_country: str = "",
) -> list[dict]:
    """Jobs seen on the board that did not match title/location filters, with reasons."""
    included_keys = {
        job_idempotency_key(j.get("url", ""))
        for j in scraped
    }
    expected = company_expected_locations(company, catalog_country=catalog_country)
    filtered: list[dict] = []
    seen: set[str] = set()
    for job in all_scraped:
        url = (job.get("url") or "").strip()
        if not url:
            continue
        key = job_idempotency_key(url)
        if key in included_keys or key in seen:
            continue
        title = (job.get("title") or "").strip()
        if not is_relevant(title):
            reason = explain_title_filter(title)
        elif expected:
            ok, loc_reason = job_matches_expected_locations(job, expected)
            reason = loc_reason or "location mismatch" if not ok else ""
        else:
            reason = "not matched"
        if not reason:
            continue
        filtered.append({**job, "filter_reason": reason})
        seen.add(key)
    return filtered


def _report_review_jobs(
    *,
    included: list[dict],
    filtered: list[dict],
) -> None:
    payload = {
        "included": [e for j in included if (e := _review_entry(j))],
        "filtered": [e for j in filtered if (e := _review_entry(j))],
    }
    if _review_reporter:
        _review_reporter(payload)
    _emit_panel_ipc("REVIEW", payload)


def _report_progress(
    *,
    current: int,
    total: int,
    company: str | None = None,
    status: str = "",
    new_jobs: int | None = None,
) -> None:
    payload = {
        "current": current,
        "total": total,
        "company": company,
        "status": status,
    }
    if new_jobs is not None:
        payload["new_jobs"] = int(new_jobs)
    if _progress_reporter:
        _progress_reporter(payload)
    _emit_panel_ipc("PROGRESS", payload)


async def _process_company_async(
    client: httpx.AsyncClient,
    company: dict,
    index: int,
    total: int,
    *,
    save_fn,
    enrich_only: bool,
    skip_enriched: bool,
    enrich_concurrency: int,
    review_mode: bool = False,
    catalog_country: str = "",
) -> tuple[str, int]:
    name = company["name"]
    city = company.get("city", "?")
    prefix = f"[{index}/{total}] {name} ({city})"
    company["updated"] = now_iso()

    if enrich_only:
        jobs = company.get("matching_jobs") or []
        if not jobs:
            return f"{prefix} — no jobs to enrich", 0
        jobs = await enrich_jobs_async_with_client(
            client, jobs, company,
            only_missing=skip_enriched,
            concurrency=enrich_concurrency,
            preserve_fetched=True,
        )
        company["matching_jobs"] = jobs
        company["updated"] = now_iso()
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        return (
            f"{prefix} — enriched {len(jobs)} job(s) "
            f"({sponsored} with visa/relocation support)",
            0,
        )

    try:
        raise_if_cancelled()
        existing = list(company.get("matching_jobs") or [])
        # Always scrape the full careers board, then apply keyword filters for merge.
        # Bulk fetch used to pass relevant_only=True, which skipped roles during
        # HTML/Playwright parsing and produced fewer jobs than single-company fetch.
        all_scraped = await get_jobs_async(
            client, company, save_fn=save_fn, relevant_only=False
        )
        title_matched = _filter_relevant_jobs(all_scraped, True)
        scraped, location_filtered = filter_jobs_by_expected_locations(
            title_matched,
            company,
            catalog_country=catalog_country,
        )
        if location_filtered:
            print(
                f"    Skipped {len(location_filtered)} role(s) — "
                "location outside company office tags"
            )
        if review_mode:
            filtered_out = _review_filtered_jobs(
                all_scraped,
                scraped,
                company,
                catalog_country=catalog_country,
            )
            _report_review_jobs(included=scraped, filtered=filtered_out)
        raise_if_cancelled()
        jobs, preserved, new_count, stale_kept = merge_matching_jobs(existing, scraped)
        backfill_listing_locations(jobs, title_matched)
        _report_activity("Checking visa/relocation details…")
        jobs = await enrich_jobs_async_with_client(
            client, jobs, company,
            only_missing=True,
            concurrency=enrich_concurrency,
            preserve_fetched=True,
        )
        company["matching_jobs"] = jobs
        company["updated"] = now_iso()
        if company.get("fetch_problem"):
            company.pop("fetch_problem", None)
            company.pop("fetch_problem_date", None)
        company["fetch_ok"] = True
        company["fetch_ok_date"] = today()
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        applied_n = sum(1 for j in jobs if j.get("applied"))
        extra = []
        if preserved:
            extra.append(f"{preserved} preserved")
        if new_count:
            extra.append(f"{new_count} new")
        if stale_kept:
            extra.append(f"{stale_kept} kept from cache")
        if applied_n:
            extra.append(f"{applied_n} applied")
        suffix = f" ({', '.join(extra)})" if extra else ""
        return (
            f"{prefix} — {len(jobs)} matching job(s) "
            f"({sponsored} with visa/relocation support){suffix}",
            new_count,
        )
    except FetchCancelled:
        raise
    except Exception as e:
        if not company.get("matching_jobs"):
            company["matching_jobs"] = []
        company["updated"] = now_iso()
        return f"{prefix} — Error: {e}", 0


async def run_file_async(
    country_key: str,
    *,
    target: str | None = None,
    skip_filled: bool = False,
    enrich_only: bool = False,
    skip_enriched: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> None:
    if not HTTPX_AVAILABLE:
        raise SystemExit("httpx is required for async scraping: pip install httpx")

    data = load_country(country_key) or {"companies": []}

    file_lock = threading.Lock()

    def checkpoint_company(company: dict) -> None:
        with file_lock:
            upsert_company(
                country_key,
                company,
                updated=company.get("updated") or now_iso(),
            )

    def finalize_catalog() -> None:
        _report_progress(current=work_total, total=work_total, status="saving")
        with file_lock:
            ts = now_iso()
            touch_country_meta(
                country_key,
                updated=ts,
                jobs_fetched=ts,
                total=len(data.get("companies") or []),
            )
        _report_progress(current=work_total, total=work_total, status="done")

    companies = data["companies"]
    if target:
        companies = [c for c in companies if c["name"].lower() == target.lower()]
        if not companies:
            msg = f"Company '{target}' not found in {country_key}"
            print(msg)
            raise LookupError(msg)

    work: list[tuple[dict, int]] = []
    total = len(companies)
    for i, company in enumerate(companies, 1):
        if skip_filled and company.get("matching_jobs") and not enrich_only:
            _safe_print(
                f"[{i}/{total}] {company['name']} — skipped "
                f"(already has {len(company['matching_jobs'])} jobs)"
            )
            continue
        work.append((company, i))

    if target:
        print(f"\n=== {target} ===")
    else:
        print(
            f"\n=== {country_key} ({len(work)} to process, "
            f"{concurrency} concurrent, asyncio) ==="
        )

    if not work:
        if target:
            company = next(
                (c for c in data["companies"] if c["name"].lower() == target.lower()),
                None,
            )
            if company and company.get("matching_jobs"):
                n = len(company["matching_jobs"])
                print(f"Done {target} — skipped (already has {n} matching job(s))")
            else:
                print(f"Done {target} — nothing to process")
        else:
            total_jobs = sum(len(c.get("matching_jobs", [])) for c in data["companies"])
            print(
                f"Done {country_key} — {total_jobs} matching jobs "
                f"across {len(data['companies'])} companies."
            )
        return

    work_total = len(work)
    progress = {"completed": 0}
    progress_lock = asyncio.Lock()
    _report_progress(current=0, total=work_total, status="starting")

    enrich_concurrency = max(4, min(12, concurrency * 2))
    sem = asyncio.Semaphore(max(1, concurrency))

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency),
    ) as client:

        async def bounded(item: tuple[dict, int]) -> str | None:
            company, idx = item
            name = company["name"]
            if is_cancel_requested():
                return None
            _report_progress(
                current=progress["completed"],
                total=work_total,
                company=name,
                status="fetching",
            )
            new_count = 0
            try:
                async with sem:
                    raise_if_cancelled()
                    msg, new_count = await _process_company_async(
                        client, company, idx, total,
                        save_fn=None,
                        enrich_only=enrich_only,
                        skip_enriched=skip_enriched,
                        enrich_concurrency=enrich_concurrency,
                        review_mode=bool(target),
                        catalog_country=country_key or "",
                    )
            except FetchCancelled:
                return None
            except asyncio.CancelledError:
                if is_cancel_requested():
                    return None
                raise
            _safe_print(msg)
            async with progress_lock:
                progress["completed"] += 1
                done = progress["completed"]
            _report_progress(
                current=done,
                total=work_total,
                company=name,
                status="done",
                new_jobs=new_count,
            )
            if is_cancel_requested():
                return None
            await asyncio.to_thread(checkpoint_company, company)
            return msg

        async def cancel_watcher(tasks: list[asyncio.Task]) -> None:
            while not is_cancel_requested():
                await asyncio.sleep(0.15)
            for task in tasks:
                if not task.done():
                    task.cancel()

        if concurrency <= 1:
            for item in work:
                if is_cancel_requested():
                    _safe_print("Cancelled — saved progress for completed companies")
                    finalize_catalog()
                    return
                await bounded(item)
        else:
            queue: asyncio.Queue[tuple[dict, int]] = asyncio.Queue()
            for item in work:
                queue.put_nowait(item)

            async def worker() -> None:
                while True:
                    if is_cancel_requested():
                        return
                    try:
                        item = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    await bounded(item)

            n_workers = min(concurrency, len(work))
            workers = [asyncio.create_task(worker()) for _ in range(n_workers)]
            watcher = asyncio.create_task(cancel_watcher(workers))
            try:
                await asyncio.gather(*workers, return_exceptions=True)
            finally:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher
            if is_cancel_requested():
                _safe_print("Cancelled — saved progress for completed companies")
                finalize_catalog()
                return

    finalize_catalog()
    if target:
        company = work[0][0]
        jobs = company.get("matching_jobs") or []
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        print(
            f"Done {target} — {len(jobs)} matching job(s) "
            f"({sponsored} with visa/relocation support)"
        )
    else:
        total_jobs = sum(len(c.get("matching_jobs", [])) for c in data["companies"])
        print(
            f"Done {country_key} — {total_jobs} matching jobs "
            f"across {len(data['companies'])} companies."
        )


def run_country(
    country_key: str,
    *,
    target: str | None = None,
    skip_filled: bool = False,
    enrich_only: bool = False,
    skip_enriched: bool = False,
    workers: int = DEFAULT_CONCURRENCY,
) -> None:
    asyncio.run(
        run_file_async(
            country_key,
            target=target,
            skip_filled=skip_filled,
            enrich_only=enrich_only,
            skip_enriched=skip_enriched,
            concurrency=workers,
        )
    )


def main():
    country_keys = ["germany"]
    target = None
    skip_filled = False
    enrich_only = False
    skip_enriched = False
    run_all = False
    workers = DEFAULT_WORKERS
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--skip-filled":
            skip_filled = True
        elif arg == "--enrich-only":
            enrich_only = True
        elif arg == "--skip-enriched":
            skip_enriched = True
        elif arg == "--all":
            run_all = True
        elif arg == "--serial":
            workers = 1
        elif arg == "--workers":
            i += 1
            if i >= len(args):
                print("--workers requires a number")
                return
            workers = max(1, int(args[i]))
        elif arg.startswith("--workers="):
            workers = max(1, int(arg.split("=", 1)[1]))
        elif arg == "--country":
            i += 1
            if i >= len(args):
                print("--country requires a country key (e.g. uk, germany)")
                return
            country_keys = [args[i]]
        elif arg.startswith("--country="):
            country_keys = [arg.split("=", 1)[1]]
        else:
            target = arg
        i += 1

    if run_all:
        country_keys = list(COUNTRY_FILE_NAMES.keys())

    for country_key in country_keys:
        run_country(
            country_key,
            target=target,
            skip_filled=skip_filled,
            enrich_only=enrich_only,
            skip_enriched=skip_enriched,
            workers=workers,
        )

    if len(country_keys) > 1:
        print(f"\nAll done — processed {len(country_keys)} countries.")


if __name__ == "__main__":
    main()
