"""Row and JSON serialization for catalog entities."""

from __future__ import annotations

import json

from relocation_jobs.core.location_tags import (
    format_location_display,
    normalize_locations,
    sync_company_location_fields,
)
from relocation_jobs.schemas import Location
from relocation_jobs.shared.board_contract import (
    catalog_kind_for_write,
    normalize_catalog_kind,
)

from relocation_jobs.catalog.util import row_dict, visa_from_db

def job_locations_json(job: dict) -> str:
    """Serialize job locations to JSONB-compatible string."""
    locations = job.get("locations")
    if isinstance(locations, list) and locations:
        try:
            return json.dumps([Location(**loc).model_dump() if isinstance(loc, dict) else loc for loc in locations])
        except Exception:
            pass
    return "[]"


def parse_job_locations_json(raw: str | None) -> list[Location] | None:
    """Parse JSONB locations string to Location objects."""
    if not raw or raw == "[]":
        return None
    try:
        val = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if not isinstance(val, list) or not val:
        return None
    try:
        return [Location(**item) for item in val if isinstance(item, dict)]
    except Exception:
        return None


def json_sources(company: dict) -> str:
    """Serialize sources to JSONB-compatible string."""
    sources = company.get("sources")
    if isinstance(sources, list):
        return json.dumps(sources)
    return "[]"


def parse_sources(raw: str | None) -> list[str]:
    """Parse JSONB sources string to list of source names."""
    try:
        val = json.loads(raw or "[]") if isinstance(raw, str) else (raw or [])
        if not isinstance(val, list):
            return []
        return [str(item) for item in val if item]
    except Exception:
        return []


def parse_cities_json(raw: str | None) -> list[str]:
    """Parse JSONB cities string to list of city strings."""
    try:
        val = json.loads(raw or "[]") if isinstance(raw, str) else (raw or [])
    except json.JSONDecodeError:
        return []
    if not isinstance(val, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in val:
        label = (item or "").strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def company_cities_from_row(data: dict) -> list[str]:
    cities = parse_cities_json(data.get("cities_json"))
    if cities:
        return cities
    single = (data.get("city") or "").strip()
    return [single] if single else []


def cities_json_from_company(company: dict) -> str:
    """Serialize cities list from company dict to JSONB string."""
    raw = company.get("cities")
    if isinstance(raw, list):
        cleaned = [(item or "").strip() for item in raw if (item or "").strip()]
    else:
        single = (company.get("city") or "").strip()
        cleaned = [single] if single else []
    seen: set[str] = set()
    unique: list[str] = []
    for label in cleaned:
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(label)
    unique.sort(key=lambda x: x.casefold())
    return json.dumps(unique)


def parse_locations_json(raw: str | None, *, catalog_country: str = "") -> list[Location]:
    """Parse JSONB locations string to Location objects."""
    if raw:
        try:
            val = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            val = []
        if isinstance(val, list) and val and isinstance(val[0], dict):
            normalized = normalize_locations(val, catalog_country=catalog_country)
            return [Location(**loc) for loc in normalized if isinstance(loc, dict)]
    cities = parse_cities_json(raw=None)
    if raw is None:
        cities = []
    normalized = normalize_locations(None, catalog_country=catalog_country, legacy_cities=cities)
    return [Location(**loc) for loc in normalized if isinstance(loc, dict)]


def locations_json_from_company(company: dict, *, catalog_country: str = "") -> str:
    """Serialize locations list from company dict to JSONB string."""
    sync_company_location_fields(company, catalog_country=catalog_country)
    payload = [
        Location(country=loc["country"], city=loc["city"]).model_dump()
        for loc in company.get("locations") or []
    ]
    return json.dumps(payload)


def company_row_to_dict(row, jobs: list[dict]) -> dict:
    """Convert database row to company dict using Pydantic schemas."""
    data = row_dict(row)
    catalog_country = data.get("country") or ""
    locations = parse_locations_json(
        data.get("locations_json"),
        catalog_country=catalog_country,
    )
    if not locations:
        normalized = normalize_locations(
            None,
            catalog_country=catalog_country,
            legacy_cities=parse_cities_json(data.get("cities_json")),
            legacy_city=data.get("city") or "",
        )
        locations = [Location(**loc) for loc in normalized if isinstance(loc, dict)]

    sources = parse_sources(data.get("sources_json"))
    company = {
        "name": data["name"],
        "city": " · ".join(
            format_location_display(loc.country, loc.city) for loc in locations
        ),
        "cities": [loc.city for loc in locations],
        "locations": [loc.model_dump() for loc in locations],
        "size": data.get("size") or "",
        "careers_url": data.get("careers_url") or "",
        "ats_type": data.get("ats_type") or "",
        "ats_url": data.get("ats_url") or "",
        "fetch_problem": bool(data.get("fetch_problem")),
        "fetch_problem_date": data.get("fetch_problem_date") or "",
        "fetch_ok": bool(data.get("fetch_ok")),
        "fetch_ok_date": data.get("fetch_ok_date") or "",
        "added": data.get("added") or "",
        "updated": data.get("updated") or "",
        "sources": sources,
        "catalog_kind": normalize_catalog_kind(data.get("catalog_kind"))
        if data.get("catalog_kind")
        else catalog_kind_for_write(
            country_key=catalog_country,
            ats_type=data.get("ats_type"),
            sources=sources,
        ),
        "matching_jobs": jobs,
    }
    return company


def job_row_to_dict(row) -> dict:
    """Convert database job row to dict using Pydantic schemas."""
    data = row_dict(row)
    job = {
        "title": data.get("title") or "",
        "url": data.get("url") or "",
        "fetched": data.get("fetched") or "",
        "last_seen": data.get("last_seen") or "",
        "idempotency_key": data.get("idempotency_key") or "",
        "visa_sponsorship": visa_from_db(data.get("visa_sponsorship")),
    }
    location = (data.get("location") or "").strip()
    if location:
        job["location"] = location
    locations = parse_job_locations_json(data.get("locations_json"))
    if locations:
        job["locations"] = [loc.model_dump() for loc in locations]
    return job

