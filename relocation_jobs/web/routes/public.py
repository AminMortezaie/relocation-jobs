from __future__ import annotations

from flask import request

from relocation_jobs.catalog.repo import (
    get_catalog_overview,
    list_sponsored_catalog_companies,
    list_sponsored_catalog_jobs,
    load_catalog_companies_page,
)
from relocation_jobs.core.location_tags import country_label

PREVIEW_LIMIT = 8
PREVIEW_SEARCH_LIMIT = 24
FEATURED_LIMIT = 3


def _preview_company(company: dict) -> dict:
    jobs = list(company.get("matching_jobs") or [])
    visa_jobs = sum(1 for job in jobs if job.get("visa_sponsorship") is True)
    locations = list(company.get("locations") or [])
    primary_country = (
        company.get("country")
        or (locations[0].get("country") if locations else "")
    )
    latest_fetched = company.get("latest_fetched") or (jobs[0].get("fetched") if jobs else "")
    return {
        "name": company.get("name"),
        "country": primary_country,
        "country_label": country_label(primary_country or "") if primary_country else "",
        "city": company.get("city"),
        "locations": locations,
        "ats_type": company.get("ats_type"),
        "careers_url": company.get("careers_url"),
        "latest_fetched": latest_fetched,
        "job_count": len(jobs),
        "visa_job_count": visa_jobs,
    }


def _preview_position(job: dict) -> dict:
    country = (job.get("country") or "").strip()
    return {
        "title": job.get("title") or "Untitled role",
        "url": job.get("url") or "",
        "company_name": job.get("company_name") or "",
        "country": country,
        "country_label": country_label(country) if country else "",
        "location": job.get("location") or job.get("city") or "",
        "last_seen": job.get("last_seen") or job.get("fetched") or "",
        "sponsorship_signal": "positive",
    }


def _preview_featured_company(company: dict) -> dict:
    country = (company.get("country") or "").strip()
    return {
        "name": company.get("name") or "",
        "country": country,
        "country_label": country_label(country) if country else "",
        "city": company.get("city") or "",
        "careers_url": company.get("careers_url") or "",
        "visa_role_count": int(company.get("visa_role_count") or 0),
    }


def _featured_company_rows(
    preferred_countries: list[str],
    catalog_countries: list[str],
    *,
    specific_country: bool,
) -> tuple[list[dict], str]:
    """Always return visa-positive companies users can explore.

    Prefer the requested country; if empty, widen to the full catalog so the
    homepage never shows an empty company strip.
    """
    rows = (
        list_sponsored_catalog_companies(preferred_countries, limit=FEATURED_LIMIT)
        if preferred_countries
        else []
    )
    if rows:
        return rows, "country"
    widened = list_sponsored_catalog_companies(
        catalog_countries, limit=FEATURED_LIMIT
    )
    if not widened:
        return [], ""
    return widened, ("global" if specific_country else "country")


def _public_overview_payload() -> dict:
    overview = get_catalog_overview()
    return {
        "has_data": overview.get("has_data", False),
        "countries": overview.get("countries") or [],
        "totals": overview.get("totals") or {},
        "country_meta": overview.get("country_meta") or [],
    }


def _public_preview_payload(
    *,
    limit: int = PREVIEW_LIMIT,
    country: str | None = None,
    search: str | None = None,
) -> dict:
    overview = get_catalog_overview()
    catalog_countries = [
        row.get("country")
        for row in overview.get("countries") or []
        if row.get("country")
    ]
    countries = catalog_countries
    country_key = (country or "").strip().lower()
    specific_country = bool(country_key and country_key != "all")
    if specific_country:
        countries = [key for key in countries if key == country_key]
    query = (search or "").strip() or None
    fetch_limit = limit if not query and not country_key else max(limit, PREVIEW_SEARCH_LIMIT)
    company_rows = (
        load_catalog_companies_page(
            countries,
            offset=0,
            limit=fetch_limit,
            search=query,
        )
        if countries
        else []
    )
    companies = [_preview_company(company) for _, company in company_rows]
    companies = companies[:limit]
    sponsored_jobs = list_sponsored_catalog_jobs(
        countries,
        limit=limit,
        search=query,
    )
    positions = [_preview_position(job) for job in sponsored_jobs]
    preferred = countries if countries else (
        [country_key] if specific_country else catalog_countries
    )
    featured_rows, featured_scope = _featured_company_rows(
        preferred,
        catalog_countries,
        specific_country=specific_country,
    )
    featured_companies = [
        _preview_featured_company(company) for company in featured_rows
    ]
    return {
        "companies": companies,
        "featured_companies": featured_companies,
        "positions": positions,
        "meta": {
            "limit": limit,
            "returned": len(companies),
            "positions_returned": len(positions),
            "featured_scope": featured_scope,
            "country": country_key or "all",
            "q": query or "",
            "sponsorship_filter": "positive_only",
        },
    }


def register(app):
    @app.get("/api/public/overview")
    def api_public_overview():
        return _public_overview_payload()

    @app.get("/api/public/preview")
    def api_public_preview():
        country = request.args.get("country", "").strip().lower() or None
        search = request.args.get("q", "").strip() or None
        try:
            limit = int(request.args.get("limit", PREVIEW_LIMIT))
        except ValueError:
            limit = PREVIEW_LIMIT
        limit = max(1, min(limit, PREVIEW_SEARCH_LIMIT))
        return _public_preview_payload(limit=limit, country=country, search=search)
