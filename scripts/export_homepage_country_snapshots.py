#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS_PATH = ROOT / "homepage" / "data" / "countries.json"
OUT = ROOT / "homepage" / "data" / "country-snapshots.json"
FEATURED_LIMIT = 6
POSITION_LIMIT = 8
CITY_LIMIT = 8


def _load_marketing_keys() -> list[str]:
    if not LABELS_PATH.is_file():
        return ["germany", "ireland", "netherlands", "portugal", "uk"]
    raw = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []
    return sorted(key for key in raw if isinstance(key, str) and key.strip())


def _city_labels(companies: list[dict]) -> list[str]:
    seen: set[str] = set()
    cities: list[str] = []
    for company in companies:
        for loc in company.get("locations") or []:
            city = (loc.get("city") or "").strip()
            if not city:
                continue
            key = city.casefold()
            if key in seen:
                continue
            seen.add(key)
            cities.append(city)
            if len(cities) >= CITY_LIMIT:
                return cities
        city_field = (company.get("city") or "").strip()
        if city_field and "·" not in city_field:
            bare = city_field.split("(")[0].strip()
            key = bare.casefold()
            if bare and key not in seen:
                seen.add(key)
                cities.append(bare)
                if len(cities) >= CITY_LIMIT:
                    return cities
    return cities


def _snapshot_for_country(country: str, overview_row: dict | None, meta_row: dict | None) -> dict:
    from relocation_jobs.web.routes.public import _public_preview_payload

    preview = _public_preview_payload(limit=FEATURED_LIMIT, country=country, search=None)
    companies = list(preview.get("companies") or [])
    featured = list(preview.get("featured_companies") or [])
    featured_scope = (preview.get("meta") or {}).get("featured_scope") or ""
    if featured_scope != "country":
        featured = []
    positions = [
        {
            "title": row.get("title") or "",
            "company_name": row.get("company_name") or "",
            "location": row.get("location") or "",
            "url": row.get("url") or "",
        }
        for row in (preview.get("positions") or [])[:POSITION_LIMIT]
        if (row.get("country") or "").strip().lower() == country
    ]
    sample_companies = [
        {
            "name": row.get("name") or "",
            "city": row.get("city") or "",
            "careers_url": row.get("careers_url") or "",
            "job_count": int(row.get("job_count") or 0),
            "visa_job_count": int(row.get("visa_job_count") or 0),
        }
        for row in companies[:FEATURED_LIMIT]
    ]
    if not sample_companies and featured:
        sample_companies = [
            {
                "name": row.get("name") or "",
                "city": row.get("city") or "",
                "careers_url": row.get("careers_url") or "",
                "job_count": 0,
                "visa_job_count": int(row.get("visa_role_count") or 0),
            }
            for row in featured[:FEATURED_LIMIT]
        ]
    row = overview_row or {}
    meta = meta_row or {}
    return {
        "country": country,
        "label": row.get("label") or meta.get("label") or country,
        "companies": int(row.get("companies") or 0),
        "jobs": int(row.get("jobs") or 0),
        "visa_jobs": int(row.get("visa_jobs") or 0),
        "last_fetch": meta.get("last_fetch") or meta.get("updated") or "",
        "cities": _city_labels(companies),
        "sample_companies": sample_companies,
        "sample_positions": positions,
    }


def main() -> int:
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    from relocation_jobs.catalog.repo import get_catalog_overview

    keys = _load_marketing_keys()
    overview = get_catalog_overview()
    by_country = {
        row.get("country"): row
        for row in overview.get("countries") or []
        if row.get("country")
    }
    meta_by_country = {
        row.get("country"): row
        for row in overview.get("country_meta") or []
        if row.get("country")
    }
    snapshots = {
        key: _snapshot_for_country(key, by_country.get(key), meta_by_country.get(key))
        for key in keys
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_note": "Build-time catalog snapshot for country marketing pages.",
        "countries": snapshots,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(snapshots)} country snapshots to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
