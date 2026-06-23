"""Company catalog and tracking business logic.

No raw SQL here — all DB access goes through catalog_db or db/.
Service layer: uses Pydantic schemas for input validation and response validation.
All public functions return dicts complying with the schemas documented in their docstrings.
See SCHEMAS.md for full schema definitions.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from relocation_jobs.core.slug import slug_from_name
from relocation_jobs.catalog_db import (
    delete_company,
    get_company,
    insert_jobs,
    rename_company_in_catalog,
    update_company_fields,
    update_company_location,
    upsert_company as upsert_company_catalog,
)
from relocation_jobs.core.paths import COUNTRY_FILE_NAMES
from relocation_jobs.db import (
    clear_company_tracking,
    rename_company_tracking,
    set_company_applied_db,
    set_company_awaiting_response_db,
)
from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
)
from relocation_jobs.core.location_tags import (
    COUNTRY_LABELS,
    normalize_location,
    sync_company_location_fields,
)
from relocation_jobs.services.catalog_service import now_iso, today
from relocation_jobs.schemas import CompanyCreateInput, CompanyResponse

from relocation_jobs.core.ats_constants import ATS_TYPE_CHOICES, KNOWN_ATS
from relocation_jobs.core.ats_detection import (
    detect_ats_for_hint,
    detect_ats_static,
    detect_ats_via_playwright,
)

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
# Pure in-memory search helpers (operate on any dict, no DB calls)
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean_city(raw: str, country_key: str) -> str:
    city = raw.strip()
    pat = _CITY_SUFFIX.get(country_key)
    if pat:
        city = pat.sub("", city).strip()
    return city.split(",")[0].strip() if city else ""


def _build_locations(
    country_key: str,
    cities: list[str] | str | None,
    locations: list[dict] | None,
) -> list[dict]:
    """Normalise and deduplicate location inputs into a canonical list."""
    seen: set[str] = set()
    cleaned: list[dict] = []

    if locations is not None:
        for item in locations:
            if not isinstance(item, dict):
                continue
            loc = normalize_location(item.get("country", ""), item.get("city", ""))
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)
    elif isinstance(cities, str):
        loc = normalize_location(country_key, (cities or "").strip())
        if loc:
            cleaned = [loc]
    elif isinstance(cities, list):
        for item in cities:
            loc = normalize_location(country_key, (item or "").strip())
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)

    cleaned.sort(key=lambda x: (x["country_label"], x["city"].casefold()))
    return cleaned


# ---------------------------------------------------------------------------
# URL / string normalization
# ---------------------------------------------------------------------------

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
    if hint and hint not in ("auto", ""):
        ats_type, ats_url = detect_ats_for_hint(name, careers_url, hint)
        if ats_type:
            return _finalize_detected_ats(name, ats_type, ats_url)

    ats_type_val: str | None = None
    ats_url_val = ""

    if name in KNOWN_ATS:
        ats_type_val, ats_url_val = KNOWN_ATS[name]
    else:
        ats_type_val, ats_url_val = detect_ats_static(careers_url)
        if not ats_type_val:
            ats_type_val, ats_url_val = detect_ats_via_playwright(careers_url)

    return _finalize_detected_ats(name, ats_type_val or "", ats_url_val or "")


# ---------------------------------------------------------------------------
# Country / metadata resolution
# ---------------------------------------------------------------------------

def fetch_relocate_metadata(name: str, country_key: str | None = None) -> dict:
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
    """Create enriched company dict with ATS detection and metadata.

    Returns dict complying with CompanyCreateInput schema.
    """
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
    CompanyCreateInput(**company)
    return company


# ---------------------------------------------------------------------------
# Company lookup helpers
# ---------------------------------------------------------------------------

def resolve_company_name(country_key: str, company_name: str) -> str:
    """Get canonical company name (case-insensitive lookup).

    Raises LookupError if company not found.
    """
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return company["name"]


def touch_company_fetch_time(country_key: str, company_name: str) -> str:
    """Update company's last-updated timestamp.

    Returns ISO date string of update time.
    """
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    ts = now_iso()
    update_company_fields(country_key, company["name"], updated=ts)
    return ts


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------

def add_company(
    name: str,
    careers_url: str,
    country_key: str | None = None,
    *,
    country_keys: list[str] | None = None,
    ats_hint: str | None = None,
    locations: list[dict] | None = None,
) -> dict:
    """Add a new company to the catalog with validation.

    Returns dict complying with CompanyResponse schema.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Company name is required")

    CompanyCreateInput(name=name, careers_url=careers_url)

    careers_url = normalize_careers_url(careers_url)
    hint = None
    if country_keys:
        cleaned_keys = [k.strip().lower() for k in country_keys if k.strip().lower() in COUNTRY_FILE_NAMES]
        hint = cleaned_keys[0] if cleaned_keys else None
    elif country_key and country_key not in ("auto", "all", ""):
        hint = country_key.strip().lower()

    resolved_country, _meta = resolve_country_key(name, careers_url, hint=hint)
    if resolved_country not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {resolved_country}")

    if get_company(resolved_country, name) is not None:
        raise LookupError(f"Company already exists: {name}")

    company = enrich_new_company(name, careers_url, resolved_country, ats_hint=ats_hint)

    if locations is not None:
        company["locations"] = _build_locations(resolved_country, None, locations)
        sync_company_location_fields(company, catalog_country=resolved_country)

    upsert_company_catalog(resolved_country, company)

    return {
        "country": resolved_country,
        "country_label": COUNTRY_LABELS.get(resolved_country, resolved_country),
        **company,
    }


def rename_company(country_key: str, company_name: str, new_name: str) -> dict:
    """Rename a company in catalog and user tracking.

    Returns dict with rename confirmation and company details.
    """
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

    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    if get_company(country_key, new_name) is not None:
        raise LookupError(f"Company already exists: {new_name}")

    canonical_old = company["name"]
    rename_company_in_catalog(country_key, canonical_old, new_name)
    rename_company_tracking(country_key, canonical_old, new_name)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
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
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    careers_url = normalize_careers_url(careers_url)
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    canonical_name = company["name"]
    fields: dict = {"careers_url": careers_url, "updated": today()}
    if redetect_ats:
        ats_type, ats_url = detect_ats_for_company(canonical_name, careers_url)
        fields.update(ats_type=ats_type, ats_url=ats_url)

    update_company_fields(country_key, canonical_name, **fields)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": canonical_name,
        "careers_url": careers_url,
        "ats_type": fields.get("ats_type", company.get("ats_type", "")),
        "ats_url": fields.get("ats_url", company.get("ats_url", "")),
        "redetect_ats": redetect_ats,
    }


def update_company_city(
    country_key: str,
    company_name: str,
    cities: list[str] | str | None = None,
    *,
    locations: list[dict] | None = None,
) -> dict:
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    cleaned = _build_locations(country_key, cities, locations)
    update_company_location(country_key, company["name"], cleaned)

    temp = {"locations": cleaned}
    sync_company_location_fields(temp, catalog_country=country_key)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": company["name"],
        "city": temp.get("city") or "",
        "cities": temp.get("cities") or [],
        "locations": cleaned,
    }


def add_manual_jobs(country_key: str, company_name: str, jobs: list[dict]) -> dict:
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    ts = today()
    to_add = [
        {"title": (j.get("title") or "").strip(), "url": normalize_job_url(j.get("url") or ""), "fetched": ts, "last_seen": ts}
        for j in jobs
        if (j.get("title") or "").strip() and normalize_job_url(j.get("url") or "")
    ]
    if not to_add:
        raise ValueError("No valid jobs to add")

    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    existing_total = len(company.get("matching_jobs") or [])
    new_count = insert_jobs(country_key, company["name"], to_add)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": company["name"],
        "added": new_count,
        "total": existing_total + new_count,
    }


def set_company_fetch_problem(
    country_key: str,
    company_name: str,
    fetch_problem: bool,
    *,
    mark_fetch_ok: bool = False,
) -> dict:
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    ts = today()
    canonical_name = company["name"]

    if fetch_problem:
        update_company_fields(
            country_key, canonical_name,
            fetch_problem=1, fetch_problem_date=ts,
            fetch_ok=0, fetch_ok_date=None, updated=ts,
        )
        result_fp, result_fpd = True, ts
        result_fo, result_fod = False, ""
    else:
        fields: dict = {"fetch_problem": 0, "fetch_problem_date": None, "updated": ts}
        if mark_fetch_ok:
            fields.update(fetch_ok=1, fetch_ok_date=ts)
            result_fo, result_fod = True, ts
        else:
            result_fo = bool(company.get("fetch_ok"))
            result_fod = company.get("fetch_ok_date") or ""
        update_company_fields(country_key, canonical_name, **fields)
        result_fp, result_fpd = False, ""

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": canonical_name,
        "fetch_problem": result_fp,
        "fetch_problem_date": result_fpd,
        "fetch_ok": result_fo,
        "fetch_ok_date": result_fod,
    }


def set_company_fetch_ok(country_key: str, company_name: str) -> dict:
    return set_company_fetch_problem(country_key, company_name, False, mark_fetch_ok=True)


def remove_company(country_key: str, company_name: str) -> dict:
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILE_NAMES:
        raise ValueError(f"Unknown country: {country_key}")

    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    canonical_name = company["name"]
    removed_jobs = len(company.get("matching_jobs") or [])
    delete_company(country_key, canonical_name)
    clear_company_tracking(country_key, canonical_name)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": canonical_name,
        "removed_jobs": removed_jobs,
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
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return set_company_applied_db(user_id, country_key, company["name"], applied)


def set_company_awaiting_response(
    country_key: str,
    company_name: str,
    awaiting: bool,
    *,
    user_id: int,
) -> dict:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return set_company_awaiting_response_db(user_id, country_key, company["name"], awaiting)
