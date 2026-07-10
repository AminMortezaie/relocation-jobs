from __future__ import annotations

from relocation_jobs.catalog.repo import get_catalog_overview, load_catalog_companies_page
from relocation_jobs.core.location_tags import country_label

PREVIEW_LIMIT = 8
PREVIEW_SEARCH_LIMIT = 24
PREVIEW_JOB_LIMIT = 2


def _preview_job(job: dict) -> dict:
    return {
        "title": job.get("title"),
        "url": job.get("url"),
        "visa_sponsorship": job.get("visa_sponsorship"),
        "fetched": job.get("fetched"),
    }


def _preview_company(company: dict) -> dict:
    jobs = list(company.get("matching_jobs") or [])
    preview_jobs = jobs[:PREVIEW_JOB_LIMIT]
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
        "preview_jobs": [_preview_job(job) for job in preview_jobs],
    }


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
    countries = [
        row.get("country")
        for row in overview.get("countries") or []
        if row.get("country")
    ]
    country_key = (country or "").strip().lower()
    if country_key and country_key != "all":
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
    if query:
        needle = query.lower()
        companies = [
            company
            for company in companies
            if needle in (company.get("name") or "").lower()
            or needle in (company.get("country_label") or "").lower()
            or any(
                needle in (job.get("title") or "").lower()
                for job in company.get("preview_jobs") or []
            )
        ]
    companies = companies[:limit]
    return {
        "companies": companies,
        "meta": {
            "limit": limit,
            "returned": len(companies),
            "country": country_key or "all",
            "q": query or "",
        },
    }


def register(app):
    @app.get("/api/public/overview")
    def api_public_overview():
        return _public_overview_payload()

    @app.get("/api/public/preview")
    def api_public_preview():
        from flask import request

        country = request.args.get("country", "").strip().lower() or None
        search = request.args.get("q", "").strip() or None
        try:
            limit = int(request.args.get("limit", PREVIEW_LIMIT))
        except ValueError:
            limit = PREVIEW_LIMIT
        limit = max(1, min(limit, PREVIEW_SEARCH_LIMIT))
        return _public_preview_payload(limit=limit, country=country, search=search)
