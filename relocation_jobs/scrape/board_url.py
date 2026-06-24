from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from relocation_jobs.core.location_tags import (
    COUNTRY_LABELS,
    company_expected_locations,
    normalize_country_key,
)


def _location_search_labels(company: dict, *, catalog_country: str = "") -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for loc in company_expected_locations(company, catalog_country=catalog_country):
        country = normalize_country_key(str(loc.get("country") or ""))
        label = (
            str(loc.get("country_label") or "").strip()
            or COUNTRY_LABELS.get(country, "")
        )
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    if labels:
        return labels
    if catalog_country:
        country = normalize_country_key(catalog_country)
        label = COUNTRY_LABELS.get(country, "")
        if label:
            return [label]
    return []


def _scope_sap_jobs_url(url: str, company: dict, *, catalog_country: str = "") -> str:
    parsed = urlparse(url)
    if "jobs.sap.com" not in (parsed.netloc or "").lower():
        return url
    qs = parse_qs(parsed.query, keep_blank_values=True)
    if "locationsearch" not in qs:
        return url
    current = (qs.get("locationsearch") or [""])[0].strip()
    if current:
        return url
    labels = _location_search_labels(company, catalog_country=catalog_country)
    if not labels:
        return url
    qs["locationsearch"] = [labels[0]]
    return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))


def resolve_generic_board_url(
    company: dict,
    board_url: str,
    *,
    catalog_country: str = "",
) -> str:
    """Return a careers listing URL scoped to the company's office tags when possible."""
    page_url = (company.get("careers_url") or board_url or "").strip()
    if not page_url:
        return ""
    return _scope_sap_jobs_url(page_url, company, catalog_country=catalog_country)
