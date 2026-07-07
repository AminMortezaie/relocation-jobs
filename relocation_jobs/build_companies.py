#!/usr/bin/env python3
"""
Discover careers URLs for companies in {country}_companies.json and sort the list.

Sort order:
  1. City (A–Z)
  2. Company size (smallest range first, e.g. 11–50 before 501–1,000)
  3. Company name (A–Z)

Careers discovery:
  1. Relocate.me company page (jobs/careers website link when present)
  2. Static HTTP: nav/footer links + common /careers, /jobs paths
  3. Playwright: JS homepages + follow buttons like "Open positions", "View jobs"

Usage:
    python3 scripts/build_companies.py netherlands
    python3 scripts/build_companies.py uk
    python3 scripts/build_companies.py netherlands --sort-only
    python3 scripts/build_companies.py uk "Monzo"
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from relocation_jobs.catalog.repo import load_country_catalog as load_country_catalog_db
from relocation_jobs.catalog.writes import save_country_catalog as save_country_catalog_db
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, supported_countries
from relocation_jobs.core.slug import slug_from_name

from playwright.sync_api import sync_playwright

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT_FETCH = 15
TIMEOUT_HEAD = 8
TIMEOUT_PAGE_LOAD = 25000
TIMEOUT_PAGE_SETTLE = 2000
TIMEOUT_BUTTON_SETTLE = 2500
TIMEOUT_BUTTON_CLICK = 5000

COUNTRY_CLI_ALIASES = {
    "germany": "germany_companies.json",
    "de": "germany_companies.json",
    "netherlands": "netherlands_companies.json",
    "nl": "netherlands_companies.json",
    "uk": "uk_companies.json",
    "england": "uk_companies.json",
    "united-kingdom": "uk_companies.json",
    "portugal": "portugal_companies.json",  # add this
    "pt": "portugal_companies.json",        # add this
}

CAREER_TEXT = re.compile(
    r"career|job|vacanc|opening|position|join\s+us|work\s+with\s+us|"
    r"hiring|karriere|stellen|open\s+roles|see\s+roles|view\s+jobs",
    re.I,
)
ATS_HOST = re.compile(
    r"greenhouse\.io|lever\.co|ashbyhq|personio|workable\.com|recruitee|"
    r"smartrecruiters|teamtailor|bamboohr|jobvite|icims|pinpointhq",
    re.I,
)
FOLLOW_BUTTON_TEXT = re.compile(
    r"open\s+position|view\s+(all\s+)?job|see\s+(all\s+)?job|browse\s+job|"
    r"current\s+opening|explore\s+role|view\s+opening|all\s+position|"
    r"job\s+opening|see\s+opportunit",
    re.I,
)
SKIP_HOST = re.compile(
    r"linkedin\.com|facebook\.com|twitter\.com|x\.com|instagram\.com|"
    r"youtube\.com|github\.com|relocate\.me|google\.com|apple\.com",
    re.I,
)

SIZE_ORDER = [
    (2, "2-10"),
    (11, "11-50"),
    (51, "51-200"),
    (201, "201-500"),
    (501, "501-1,000"),
    (1001, "1,001-5,000"),
    (10001, "10,001+"),
]


def size_sort_key(size: str) -> int:
    if not size:
        return 99999
    s = size.replace(",", "").replace(" ", "").lower()
    m = re.match(r"(\d+)\+", s)
    if m:
        return int(m.group(1))
    m = re.match(r"(\d+)-(\d+)", s)
    if m:
        return int(m.group(1))
    return 99999


def company_sort_key(company: dict) -> tuple:
    city_label = (company.get("city") or "").split(",")[0].strip().lower()
    return (
        city_label,
        size_sort_key(company.get("size", "")),
        company.get("name", "").strip().lower(),
    )


def sort_companies(companies: list[dict]) -> list[dict]:
    return sorted(companies, key=company_sort_key)


def root_url(url: str) -> str:
    p = urlparse(url if "://" in url else f"https://{url}")
    return f"{p.scheme}://{p.netloc}"


def score_careers_url(url: str, link_text: str = "") -> int:
    u, t = url.lower(), link_text.lower()
    if SKIP_HOST.search(u):
        return -1
    score = 0
    if ATS_HOST.search(u):
        score += 10
    if re.search(r"career|job|vacanc|opening|hiring|join", u):
        score += 5
    if re.search(r"career|job|vacanc|opening|hiring|join", t):
        score += 3
    if u.rstrip("/").count("/") <= 3:
        score += 1
    if any(x in u for x in ("/about", "/blog", "/press", "/news", "/privacy")):
        score -= 3
    return score


def pick_best(candidates: list[tuple[int, str]]) -> str | None:
    valid = [(s, u) for s, u in candidates if s >= 0 and u]
    if not valid:
        return None
    valid.sort(key=lambda x: (-x[0], len(x[1])))
    return valid[0][1]


def fetch_html(url: str) -> tuple[str | None, str | None]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_FETCH, allow_redirects=True)
        if r.status_code >= 400:
            return None, None
        return r.text, r.url
    except requests.RequestException:
        return None, None


def probe_common_paths(base_url: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    root = root_url(base_url)
    paths = [
        "/careers",
        "/jobs",
        "/careers/",
        "/jobs/",
        "/company/careers",
        "/about/careers",
        "/work-with-us",
        "/join-us",
        "/en/careers",
        "/en/jobs",
        "/karriere",
        "/vacancies",
    ]
    for path in paths:
        url = root + path
        try:
            r = requests.head(url, headers=HEADERS, timeout=TIMEOUT_HEAD, allow_redirects=True)
            if r.status_code < 400:
                found.append((score_careers_url(r.url), r.url))
        except requests.RequestException:
            pass
    return found


def extract_link_candidates(html: str, page_url: str) -> list[tuple[int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"].strip())
        if not href.startswith("http"):
            continue
        text = a.get_text(" ", strip=True)
        if ATS_HOST.search(href):
            candidates.append((score_careers_url(href, text) + 5, href))
            continue
        if CAREER_TEXT.search(text) or CAREER_TEXT.search(href):
            candidates.append((score_careers_url(href, text), href))
    return candidates


def discover_from_relocate(name: str) -> str | None:
    slug = slug_from_name(name)
    for s in {slug, slug.replace("-", "")}:
        html, final = fetch_html(f"https://relocate.me/companies-hiring/{s}")
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        fallback = None
        for a in soup.select("a.company-links__link, a.website-link"):
            href = a.get("href", "")
            text = a.get_text(strip=True).lower()
            if not href.startswith("http"):
                continue
            if "job" in href.lower() or "career" in href.lower():
                return href
            if text == "official website":
                # May be jobs subdomain (e.g. jobs.blablacar.com)
                if re.search(r"job|career", href, re.I):
                    return href
                fallback = href
        if fallback:
            return fallback
    return None


def discover_careers_static(start_url: str) -> str | None:
    if not start_url.startswith("http"):
        start_url = f"https://{start_url}"

    candidates: list[tuple[int, str]] = []
    html, final = fetch_html(start_url)
    if html and final:
        candidates.extend(extract_link_candidates(html, final))
        candidates.extend(probe_common_paths(final))

    return pick_best(candidates)


def _find_page_link_candidates(page, page_url: str) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    for a in page.query_selector_all("a[href]"):
        href = a.get_attribute("href") or ""
        text = (a.inner_text() or "").strip()
        full = urljoin(page_url, href)
        if not full.startswith("http"):
            continue
        if ATS_HOST.search(full) or CAREER_TEXT.search(text) or CAREER_TEXT.search(full):
            candidates.append((score_careers_url(full, text), full))
    return candidates


def _handle_cta_button(el, page, base_url: str) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    try:
        text = (el.inner_text() or "").strip()
    except Exception:
        return candidates

    if not text or not FOLLOW_BUTTON_TEXT.search(text):
        return candidates

    try:
        if el.evaluate("el => el.tagName.toLowerCase()") == "a":
            href = el.get_attribute("href")
            if href:
                full = urljoin(base_url, href)
                if full.startswith("http"):
                    candidates.append((score_careers_url(full, text) + 4, full))
        else:
            el.click(timeout=TIMEOUT_BUTTON_CLICK)
            page.wait_for_timeout(TIMEOUT_BUTTON_SETTLE)
            sub = page.url
            candidates.append((score_careers_url(sub, text) + 4, sub))
            for a in page.query_selector_all("a[href]"):
                href = a.get_attribute("href") or ""
                full = urljoin(sub, href)
                if ATS_HOST.search(full) or CAREER_TEXT.search(full):
                    candidates.append((score_careers_url(full), full))
    except Exception:
        pass

    return candidates


def discover_careers_playwright(start_url: str) -> str | None:
    candidates: list[tuple[int, str]] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
                page.wait_for_timeout(TIMEOUT_PAGE_SETTLE)
                final = page.url

                candidates.extend(_find_page_link_candidates(page, final))
                candidates.extend(probe_common_paths(final))

                for el in page.query_selector_all("a, button"):
                    candidates.extend(_handle_cta_button(el, page, final))
            except Exception:
                pass
            finally:
                browser.close()
    except Exception:
        return None

    return pick_best(candidates)


def discover_careers_url(company: dict) -> str:
    name = company["name"]
    start = company.get("careers_url") or ""

    relocate_url = discover_from_relocate(name)
    if relocate_url and score_careers_url(relocate_url) >= 5:
        return relocate_url

    for url in filter(None, [start, relocate_url]):
        found = discover_careers_static(url)
        if found and score_careers_url(found) >= 5:
            return found

    for url in filter(None, [start, relocate_url]):
        found = discover_careers_playwright(url)
        if found:
            return found

    return start or relocate_url or ""


def _resolve_country_key(country: str) -> str:
    alias = country.lower()
    known = supported_countries()
    if alias in known:
        return alias
    filename = COUNTRY_CLI_ALIASES.get(alias)
    if filename:
        for key, name in COUNTRY_ARCHIVE_FILENAMES.items():
            if name == filename:
                return key
    raise SystemExit(
        f"Unknown country '{country}'. Use: {', '.join(sorted(known))}"
    )


def load_country(country: str) -> tuple[dict, str]:
    country_key = _resolve_country_key(country)
    data = load_country_catalog_db(country_key)
    if data is None:
        data = {"companies": [], "total": 0}
    return data, country_key


def save_country(country_key: str, data: dict) -> None:
    data["companies"] = sort_companies(data["companies"])
    save_country_catalog_db(country_key, data)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--sort-only"]
    sort_only = "--sort-only" in sys.argv
    if not args:
        raise SystemExit("Usage: python3 scripts/build_companies.py <country> [--sort-only] [Company Name]")

    country = args[0]
    target = args[1] if len(args) > 1 else None
    data, country_key = load_country(country)
    companies = data["companies"]

    if target:
        companies = [c for c in companies if c["name"].lower() == target.lower()]
        if not companies:
            raise SystemExit(f"Company '{target}' not found")

    total = len(companies)
    for i, company in enumerate(companies, 1):
        name = company["name"]
        if sort_only:
            print(f"[{i}/{total}] {name} — sort only")
            continue

        old = company.get("careers_url", "")
        print(f"[{i}/{total}] {name} …", end=" ", flush=True)
        new = discover_careers_url(company)
        company["careers_url"] = new
        mark = "✓" if new and new != old else ("=" if new == old else "?")
        print(f"{mark} {new or '(none)'}")
        time.sleep(0.3)

    save_country(country_key, data)
    print(f"\nSaved {len(companies)} companies, sorted by city → size → name")


if __name__ == "__main__":
    main()
