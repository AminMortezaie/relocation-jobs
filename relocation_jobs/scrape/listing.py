"""Shared job-listing helpers (HTML parse, location text, relevance filter)."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.relevance import is_relevant

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


def filter_relevant_jobs(jobs: list[dict], relevant_only: bool) -> list[dict]:
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


def listing_job(
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


def workable_location_text(raw: dict | None) -> str:
    if not isinstance(raw, dict):
        return ""
    parts = [
        (raw.get("city") or "").strip(),
        (raw.get("region") or "").strip(),
        (raw.get("country") or "").strip(),
    ]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def smartrecruiters_location_text(raw: dict | None) -> str:
    if not isinstance(raw, dict):
        return ""
    full = (raw.get("fullLocation") or raw.get("full_location") or "").strip()
    if full:
        return full
    parts = [(raw.get("city") or "").strip(), (raw.get("country") or "").strip()]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def bamboohr_location_text(item: dict) -> str:
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


def normalize_title(text: str) -> str:
    return " ".join((text or "").split())


def title_from_listing_anchor(a) -> str:
    """Best-effort title from a listing-page job link."""
    title = normalize_title(a.get_text(" ", strip=True))
    if title.lower() not in GENERIC_LINK_LABELS and len(title) >= 5:
        if "job family" not in title.lower():
            return title[:150]

    node = a.parent
    best = ""
    for _ in range(8):
        if not node:
            break
        t = normalize_title(node.get_text(" ", strip=True))
        lower = t.lower()
        if "job family" in lower:
            t = re.split(r"job family", t, maxsplit=1, flags=re.I)[0].strip()
        if len(t) > len(best):
            best = t
        node = node.parent
    return best[:150]


def fetch_job_detail_title(url: str) -> str:
    """Load a job detail page and read the real title (h1 / og:title)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code >= 400:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        h1 = soup.find("h1")
        if h1:
            t = normalize_title(h1.get_text(" ", strip=True))
            if t:
                return t[:150]
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            t = normalize_title(og["content"])
            t = re.sub(r"\s*[-|–]\s*[^-|–]+ careers\s*$", "", t, flags=re.I)
            return t[:150]
    except Exception:
        pass
    return ""


def needs_detail_title(guess: str) -> bool:
    t = normalize_title(guess).lower()
    if not t or t in GENERIC_LINK_LABELS or len(t) < 5:
        return True
    if "job family" in t and len(guess) > 80:
        return True
    if not is_relevant(guess):
        return True
    return False


def is_listing_noise_url(url: str) -> bool:
    return bool(_LISTING_NOISE_URL.search(url or ""))


def collect_listing_job_links(soup, page_url: str) -> dict[str, str]:
    candidates: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        full_url = urljoin(page_url, a["href"])
        if full_url.rstrip("/") == page_url.rstrip("/"):
            continue
        if is_listing_noise_url(full_url):
            continue
        if not JOB_DETAIL_PATH.search(full_url):
            continue
        guess = title_from_listing_anchor(a)
        if _JUNK_LISTING_TITLE.match(normalize_title(guess)):
            continue
        prev = candidates.get(full_url)
        if not prev or len(guess) > len(prev):
            candidates[full_url] = guess
    return candidates


def listing_candidates_to_jobs(
    candidates: dict[str, str],
    *,
    relevant_only: bool = True,
) -> list[dict]:
    jobs: list[dict] = []
    for job_url, guess in candidates.items():
        if is_listing_noise_url(job_url):
            continue
        title = normalize_title(guess)
        if needs_detail_title(guess):
            detail = fetch_job_detail_title(job_url)
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


def jobs_from_listing_html(
    html: str,
    page_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = collect_listing_job_links(soup, page_url)
    return listing_candidates_to_jobs(candidates, relevant_only=relevant_only)


async def jobs_from_listing_html_async(
    html: str,
    page_url: str,
    client: httpx.AsyncClient,
    *,
    relevant_only: bool = True,
    detail_fetcher=fetch_job_detail_title,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = collect_listing_job_links(soup, page_url)
    jobs: list[dict] = []

    async def resolve_one(job_url: str, guess: str) -> dict | None:
        title = normalize_title(guess)
        if needs_detail_title(guess):
            detail = await asyncio.to_thread(detail_fetcher, job_url)
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
