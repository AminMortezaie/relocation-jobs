from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.relevance import is_relevant

_GENERIC_LINK_LABELS = frozenset({
    "view job", "view role", "view position", "see job", "see role",
    "apply", "apply now", "read more", "learn more", "details",
})

_JOB_DETAIL_PATH = re.compile(r"/job[s]?/", re.I)
_CAREERS_INDEX_SEGMENTS = frozenset({
    "careers", "jobs", "job-openings", "vacancies", "vacatures",
})
_LISTING_NOISE_URL = re.compile(r"/jobs/show_more\b", re.I)
_JUNK_LISTING_TITLE = re.compile(
    r"^(show\s+\d+\s+more|load\s+more|view\s+all(\s+jobs)?|see\s+all(\s+jobs)?)$",
    re.I,
)


def _normalize_title(text: str) -> str:
    return " ".join((text or "").split())


def _title_from_listing_anchor(a) -> str:
    title = _normalize_title(a.get_text(" ", strip=True))
    if title.lower() not in _GENERIC_LINK_LABELS and len(title) >= 5:
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
    try:
        response = requests.get(url, headers=HEADERS, timeout=12)
        if response.status_code >= 400:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
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
    if not t or t in _GENERIC_LINK_LABELS or len(t) < 5:
        return True
    if "job family" in t and len(guess) > 80:
        return True
    if not is_relevant(guess):
        return True
    return False


def _is_listing_noise_url(url: str) -> bool:
    return bool(_LISTING_NOISE_URL.search(url or ""))


def _is_careers_detail_url(url: str) -> bool:
    parts = [part for part in (urlparse(url).path or "").split("/") if part]
    if len(parts) < 2:
        return False
    if parts[0].casefold() not in _CAREERS_INDEX_SEGMENTS:
        return False
    slug = parts[-1].casefold().removesuffix(".html")
    if slug in _CAREERS_INDEX_SEGMENTS:
        return False
    if len(parts) == 2 and slug in {"en", "nl", "de", "fr", "es", "it"}:
        return False
    return bool(slug)


def _is_job_detail_url(url: str) -> bool:
    return bool(_JOB_DETAIL_PATH.search(url or "")) or _is_careers_detail_url(url)


def _collect_listing_job_links(soup, page_url: str) -> dict[str, str]:
    candidates: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        full_url = urljoin(page_url, anchor["href"])
        if full_url.rstrip("/") == page_url.rstrip("/"):
            continue
        if _is_listing_noise_url(full_url):
            continue
        if not _is_job_detail_url(full_url):
            continue
        guess = _title_from_listing_anchor(anchor)
        if _JUNK_LISTING_TITLE.match(_normalize_title(guess)):
            continue
        prev = candidates.get(full_url)
        if not prev or len(guess) > len(prev):
            candidates[full_url] = guess
    return candidates


def collect_listing_job_links(soup, page_url: str) -> dict[str, str]:
    return _collect_listing_job_links(soup, page_url)


def listing_candidates_to_jobs(
    candidates: dict[str, str],
    *,
    relevant_only: bool = False,
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


def jobs_from_listing_html(
    html: str,
    page_url: str,
    *,
    relevant_only: bool = False,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = _collect_listing_job_links(soup, page_url)
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
