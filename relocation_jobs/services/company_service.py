"""Company catalog and tracking business logic.

Coordinates catalog reads/writes with the company repository (db/companies.py).
No raw SQL here — all DB access goes through db/.
"""

from __future__ import annotations

import re
import threading
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

from relocation_jobs.build_companies import slug_from_name, sort_companies
from relocation_jobs.catalog_db import (
    load_country,
    save_country,
    upsert_company as upsert_company_catalog,
)
from relocation_jobs.paths import COUNTRY_FILE_NAMES
from relocation_jobs.db import (
    clear_company_tracking,
    rename_company_tracking,
    set_company_applied_db,
    set_company_awaiting_response_db,
)
from relocation_jobs.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
    stamp_job_identity,
)
from relocation_jobs.location_tags import (
    COUNTRY_LABELS,
    normalize_location,
    sync_company_location_fields,
)
from relocation_jobs.services.catalog_service import now_iso, today

from relocation_jobs.scrape_jobs import (
    ATS_TYPE_CHOICES,
    KNOWN_ATS,
    detect_ats_for_hint,
    detect_ats_static,
    detect_ats_via_playwright,
)

_file_lock = threading.Lock()

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CITY_SUFFIX: dict[str, re.Pattern[str]] = {
    "uk": re.compile(r",?\s*UK$", re.I),
    "germany": re.compile(r",?\s*(Germany|DE)$", re.I),
    "netherlands": re.compile(r",?\s*(Netherlands|NL|The Netherlands)$", re.I),
    "portugal": re.compile(r",?\s*(Portugal|PT)$", re.I),
}

_COUNTRY_FROM_LOCATION: list[tuple[str, re.Pattern[str]]] = [
    ("uk", re.compile(r"\b(?:UK|United Kingdom|England|Scotland|Wales)\b", re.I)),
    ("germany", re.compile(r"\b(?:Germany|Deutschland|DE)\b", re.I)),
    ("netherlands", re.compile(r"\b(?:Netherlands|NL|The Netherlands|Holland)\b", re.I)),
    ("portugal", re.compile(r"\b(?:Portugal|PT)\b", re.I)),
]

_URL_COUNTRY_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("uk", re.compile(r"\.co\.uk$|\.uk$|careers\.deliveroo\.co\.uk", re.I)),
    ("germany", re.compile(r"\.de$|\.jobs\.personio\.de|karriere\.|stellen\.", re.I)),
    ("netherlands", re.compile(r"\.nl$|\.amsterdam", re.I)),
    ("portugal", re.compile(r"\.pt$|\.lisboa|\.lisbon", re.I)),
]


# ---------------------------------------------------------------------------
# Helpers (internal)
# ---------------------------------------------------------------------------




def _clean_city(raw: str, country_key: str) -> str:
    city = raw.strip()
    pat = _CITY_SUFFIX.get(country_key)
    if pat:
        city = pat.sub("", city).strip()
    return city.split(",")[0].strip() if city else ""


def parse_country_from_location(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    for key, pattern in _COUNTRY_FROM_LOCATION:
        if pattern.search(text):
            return key
    if "," in text:
        suffix = text.rsplit(",", 1)[-1].strip()
        for key, pattern in _COUNTRY_FROM_LOCATION:
            if pattern.search(suffix):
                return key
    return None


def detect_country_from_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    full = url.lower()
    for key, pattern in _URL_COUNTRY_HINTS:
        if pattern.search(host) or pattern.search(full):
            return key
    return None


# ---------------------------------------------------------------------------
# Catalog lookup helpers (used by routes)
# ---------------------------------------------------------------------------

def find_company_in_data(data: dict, company_name: str) -> dict | None:
    target = company_name.strip().lower()
    if not target:
        return None
    for company in data.get("companies", []):
        if company.get("name", "").strip().lower() == target:
            return company
    return None


def find_job_in_data(data: dict, company_name: str, job_url: str) -> dict | None:
    target_url = normalize_job_url(job_url)
    target_key = job_idempotency_key(job_url)
    for company in data.get("companies", []):
        if company.get("name", "").lower() != company_name.lower():
            continue
        for job in company.get("matching_jobs") or []:
            if normalize_job_url(job.get("url", "")) == target_url:
                return job
            if target_key and job_idempotency_key_for_job(job) == target_key:
                return job
    return None


def resolve_company_name(country_key: str, company_name: str) -> str:
    data = load_country(country_key) or {}
    company = find_company_in_data(data, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return company["name"]


def normalize_careers_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("careers_url is required")
    if not url.startswith("http"):
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError("Invalid careers URL")
    return url


def normalize_company_size(text: str) -> str:
    def _fmt(n: int) -> str:
        return f"{n:,}" if n >= 1000 else str(n)

    cleaned = re.sub(r"\s+", " ", (text or "").replace(",", "")).strip().lower()
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)", cleaned)
    if m:
        return f"{_fmt(int(m.group(1)))}-{_fmt(int(m.group(2)))}"
    m = re.search(r"(\d+)\+", cleaned)
    if m:
        return f"{_fmt(int(m.group(1)))}+"
    return ""


# ---------------------------------------------------------------------------
# ATS detection
# ---------------------------------------------------------------------------

def list_ats_types() -> list[dict]:
    return [{"id": key, "label": label} for key, label in ATS_TYPE_CHOICES]


def _finalize_detected_ats(name: str, ats_type: str, ats_url: str) -> tuple[str, str]:
    if ats_type and ats_url:
        slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
        is_proxy = "careers-analytics" in ats_url
        is_bad_slug = slug in ("embed", "jobs", "")
        if (is_bad_slug or is_proxy) and name in KNOWN_ATS:
            ats_type, ats_url = KNOWN_ATS[name]
    return ats_type or "", ats_url or ""


def detect_ats_for_company(
    name: str,
    careers_url: str,
    *,
    ats_hint: str | None = None,
) -> tuple[str, str]:
    hint = (ats_hint or "").strip().lower()
    if hint and hint not in ("auto", "") and detect_ats_for_hint:
        ats_type, ats_url = detect_ats_for_hint(name, careers_url, hint)
        if ats_type:
            return _finalize_detected_ats(name, ats_type, ats_url)

    ats_type_val: str | None = None
    ats_url_val = ""

    if name in KNOWN_ATS:
        ats_type_val, ats_url_val = KNOWN_ATS[name]
    elif detect_ats_static:
        ats_type_val, ats_url_val = detect_ats_static(careers_url)
        if not ats_type_val and detect_ats_via_playwright:
            ats_type_val, ats_url_val = detect_ats_via_playwright(careers_url)

    return _finalize_detected_ats(name, ats_type_val or "", ats_url_val or "")


# ---------------------------------------------------------------------------
# Country detection
# ---------------------------------------------------------------------------

def fetch_relocate_metadata(name: str, country_key: str | None = None) -> dict:
    from bs4 import BeautifulSoup

    slug = slug_from_name(name)
    for candidate in {slug, slug.replace("-", "")}:
        try:
            r = requests.get(
                f"https://relocate.me/companies-hiring/{candidate}",
                headers=_FETCH_HEADERS,
                timeout=15,
            )
            if r.status_code >= 400:
                continue
        except requests.RequestException:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        locations = [
            el.get_text(" ", strip=True)
            for el in soup.select(".company-location")
            if el.get_text(strip=True)
        ]

        country = country_key
        city = ""
        if not country:
            for loc in locations:
                country = parse_country_from_location(loc)
                if country:
                    city = _clean_city(loc, country)
                    break
        elif locations:
            city = _clean_city(locations[0], country)

        if not city and locations:
            city = _clean_city(locations[0], country or "uk")

        size = ""
        for heading in soup.select(".company-facts__heading"):
            label = heading.get_text(strip=True).lower()
            if "company size" not in label:
                continue
            block = heading.find_next_sibling()
            if block:
                size = normalize_company_size(block.get_text(" ", strip=True))

        if city or size or country:
            return {"city": city, "size": size, "country": country or "", "relocate_slug": candidate}
    return {}


def resolve_country_key(
    name: str,
    careers_url: str,
    *,
    hint: str | None = None,
) -> tuple[str, dict]:
    hint = (hint or "").strip().lower()
    if hint and hint not in ("auto", "all") and hint in COUNTRY_FILE_NAMES:
        return hint, {}

    meta = fetch_relocate_metadata(name)
    if meta.get("country"):
        return meta["country"], meta

    from_url = detect_country_from_url(careers_url)
    if from_url:
        return from_url, meta

    raise ValueError(
        "Could not detect country. Choose one in the form or use a careers URL "
        "with a clear region (e.g. .de, .nl, .co.uk, .pt)."
    )


# ---------------------------------------------------------------------------
# Company enrichment
# ---------------------------------------------------------------------------

def enrich_new_company(
    name: str,
    careers_url: str,
    country_key: str,
    *,
    ats_hint: str | None = None,
) -> dict:
    careers_url = normalize_careers_url(careers_url)
    meta = fetch_relocate_metadata(name, country_key)
    ats_type, ats_url = detect_ats_for_company(name, careers_url, ats_hint=ats_hint)
    now = today()
    company: dict = {
        "name": name.strip(),
        "city": meta.get("city", ""),
        "size": meta.get("size", ""),
        "careers_url": careers_url,
        "matching_jobs": [],
        "ats_type": ats_type,
        "ats_url": ats_url,
        "sources": ["panel"],
        "added": now,
        "updated": now,
    }
    sync_company_location_fields(company, catalog_country=country_key)
    return company


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------

def touch_company_fetch_time(country_key: str, company_name: str) -> str:
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    with _file_lock:
        data = load_country(country_key) or {}
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")
        ts = now_iso()
        company["updated"] = ts
        upsert_company_catalog(country_key, company, updated=ts)
        return ts


def add_company(
    name: str,
    careers_url: str,
    country_key: str | None = None,
    *,
    country_keys: list[str] | None = None,
    ats_hint: str | None = None,
    locations: list[dict] | None = None,
) -> dict:
    country_labels = COUNTRY_LABELS
    name = (name or "").strip()
    if not name:
        raise ValueError("Company name is required")

    careers_url = normalize_careers_url(careers_url)
    hint = None
    if country_keys:
        cleaned_keys = [
            key.strip().lower()
            for key in country_keys
            if (key or "").strip().lower() in COUNTRY_FILE_NAMES
        ]
        hint = cleaned_keys[0] if cleaned_keys else None
    elif country_key and country_key not in ("auto", "all", ""):
        hint = country_key.strip().lower()

    resolved_country, _meta = resolve_country_key(name, careers_url, hint=hint)

    if resolved_country not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {resolved_country}")

    company = enrich_new_company(name, careers_url, resolved_country, ats_hint=ats_hint)

    if locations is not None:
        cleaned: list[dict] = []
        seen: set[str] = set()
        for item in locations:
            if not isinstance(item, dict):
                continue
            loc = normalize_location(item.get("country", ""), item.get("city", ""))
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)
        cleaned.sort(key=lambda loc: (loc["country_label"], loc["city"].casefold()))
        company["locations"] = cleaned
        sync_company_location_fields(company, catalog_country=resolved_country)

    with _file_lock:
        data = load_country(resolved_country) or {}
        for existing in data.get("companies", []):
            if existing.get("name", "").lower() == name.lower():
                raise LookupError(f"Company already exists: {name}")
        data.setdefault("companies", []).append(company)
        data["companies"] = sort_companies(data["companies"])
        data["updated"] = today()
        save_country(resolved_country, data)

    return {
        "country": resolved_country,
        "country_label": country_labels.get(resolved_country, resolved_country),
        **company,
    }


def rename_company(country_key: str, company_name: str, new_name: str) -> dict:
    country_labels = COUNTRY_LABELS
    company_name = (company_name or "").strip()
    new_name = (new_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if not new_name:
        raise ValueError("New company name is required")
    if company_name.casefold() == new_name.casefold():
        raise ValueError("New name must be different from the current name")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    with _file_lock:
        data = load_country(country_key) or {}
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_old = company.get("name", company_name)
        for existing in data.get("companies") or []:
            if existing is company:
                continue
            if existing.get("name", "").strip().casefold() == new_name.casefold():
                raise LookupError(f"Company already exists: {new_name}")

        company["name"] = new_name
        company["updated"] = today()
        data["companies"] = sort_companies(data.get("companies") or [])
        data["updated"] = today()
        save_country(country_key, data)

    rename_company_tracking(country_key, canonical_old, new_name)

    return {
        "country": country_key,
        "country_label": country_labels.get(country_key, country_key),
        "company": new_name,
        "previous_name": canonical_old,
    }


def update_company_careers(
    country_key: str,
    company_name: str,
    careers_url: str,
    *,
    redetect_ats: bool = True,
) -> dict:
    country_labels = COUNTRY_LABELS
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    careers_url = normalize_careers_url(careers_url)

    with _file_lock:
        data = load_country(country_key) or {}
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        company["careers_url"] = careers_url
        if redetect_ats:
            ats_type, ats_url = detect_ats_for_company(canonical_name, careers_url)
            company["ats_type"] = ats_type
            company["ats_url"] = ats_url
        company["updated"] = today()
        data["updated"] = today()
        save_country(country_key, data)

    return {
        "country": country_key,
        "country_label": country_labels.get(country_key, country_key),
        "company": canonical_name,
        "careers_url": careers_url,
        "ats_type": company.get("ats_type", ""),
        "ats_url": company.get("ats_url", ""),
        "redetect_ats": redetect_ats,
    }


def update_company_city(
    country_key: str,
    company_name: str,
    cities: list[str] | str | None = None,
    *,
    locations: list[dict] | None = None,
) -> dict:
    country_labels = COUNTRY_LABELS
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    cleaned: list[dict] = []
    if locations is not None:
        seen: set[str] = set()
        for item in locations:
            if not isinstance(item, dict):
                continue
            loc = normalize_location(item.get("country", ""), item.get("city", ""))
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)
        cleaned.sort(key=lambda loc: (loc["country_label"], loc["city"].casefold()))
    elif isinstance(cities, str):
        city = (cities or "").strip()
        if city:
            loc = normalize_location(country_key, city)
            if loc:
                cleaned = [loc]
    elif isinstance(cities, list):
        seen = set()
        for item in cities:
            label = (item or "").strip()
            if not label:
                continue
            loc = normalize_location(country_key, label)
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)
        cleaned.sort(key=lambda loc: (loc["country_label"], loc["city"].casefold()))

    with _file_lock:
        data = load_country(country_key) or {}
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        company["locations"] = cleaned
        sync_company_location_fields(company, catalog_country=country_key)
        company["updated"] = today()
        data["updated"] = today()
        save_country(country_key, data)

    return {
        "country": country_key,
        "country_label": country_labels.get(country_key, country_key),
        "company": canonical_name,
        "city": company["city"],
        "cities": company.get("cities") or [],
        "locations": cleaned,
    }


def add_manual_jobs(country_key: str, company_name: str, jobs: list[dict]) -> dict:
    country_labels = COUNTRY_LABELS
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    ts = today()
    to_add: list[dict] = []
    for job in jobs:
        title = (job.get("title") or "").strip()
        url = normalize_job_url(job.get("url") or "")
        if not title or not url:
            continue
        to_add.append({"title": title, "url": url, "fetched": ts, "last_seen": ts})

    if not to_add:
        raise ValueError("No valid jobs to add")

    with _file_lock:
        data = load_country(country_key) or {}
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        merged = list(company.get("matching_jobs") or [])
        existing_keys = {
            job_idempotency_key_for_job(j)
            for j in merged
            if job_idempotency_key_for_job(j)
        }
        new_count = 0
        for job in to_add:
            key = job_idempotency_key(job.get("url", ""))
            if not key or key in existing_keys:
                continue
            stamp_job_identity(job)
            merged.append(job)
            existing_keys.add(key)
            new_count += 1

        company["matching_jobs"] = merged
        company["updated"] = ts
        data["updated"] = ts
        save_country(country_key, data)

    return {
        "country": country_key,
        "country_label": country_labels.get(country_key, country_key),
        "company": canonical_name,
        "added": new_count,
        "total": len(merged),
    }


def set_company_fetch_problem(
    country_key: str,
    company_name: str,
    fetch_problem: bool,
    *,
    mark_fetch_ok: bool = False,
) -> dict:
    country_labels = COUNTRY_LABELS
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    with _file_lock:
        data = load_country(country_key) or {}
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        if fetch_problem:
            company["fetch_problem"] = True
            company["fetch_problem_date"] = today()
            company.pop("fetch_ok", None)
            company.pop("fetch_ok_date", None)
        else:
            company.pop("fetch_problem", None)
            company.pop("fetch_problem_date", None)
            if mark_fetch_ok:
                company["fetch_ok"] = True
                company["fetch_ok_date"] = today()
        save_country(country_key, data)

    return {
        "country": country_key,
        "country_label": country_labels.get(country_key, country_key),
        "company": canonical_name,
        "fetch_problem": fetch_problem,
        "fetch_problem_date": company.get("fetch_problem_date", ""),
        "fetch_ok": bool(company.get("fetch_ok")),
        "fetch_ok_date": company.get("fetch_ok_date", ""),
    }


def set_company_fetch_ok(country_key: str, company_name: str) -> dict:
    return set_company_fetch_problem(country_key, company_name, False, mark_fetch_ok=True)


def remove_company(country_key: str, company_name: str) -> dict:
    country_labels = COUNTRY_LABELS
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    target = company_name.lower()

    with _file_lock:
        data = load_country(country_key) or {}
        companies = data.get("companies", [])
        removed: dict | None = None
        kept: list[dict] = []
        for company in companies:
            if company.get("name", "").strip().lower() == target:
                if removed is not None:
                    raise LookupError(f"Duplicate company name: {company_name}")
                removed = company
            else:
                kept.append(company)

        if removed is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = removed.get("name", company_name)
        data["companies"] = kept
        data["updated"] = today()
        save_country(country_key, data)

    clear_company_tracking(country_key, canonical_name)

    return {
        "country": country_key,
        "country_label": country_labels.get(country_key, country_key),
        "company": canonical_name,
        "removed_jobs": len(removed.get("matching_jobs") or []),
    }


# ---------------------------------------------------------------------------
# Company-level tracking
# ---------------------------------------------------------------------------

def set_company_applied(
    country_key: str,
    company_name: str,
    applied: bool,
    *,
    user_id: int,
) -> dict:
    data = load_country(country_key) or {}
    company = find_company_in_data(data, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return set_company_applied_db(user_id, country_key, company_name, applied)


def set_company_awaiting_response(
    country_key: str,
    company_name: str,
    awaiting: bool,
    *,
    user_id: int,
) -> dict:
    data = load_country(country_key) or {}
    company = find_company_in_data(data, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return set_company_awaiting_response_db(user_id, country_key, company_name, awaiting)
