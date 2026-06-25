from __future__ import annotations

from relocation_jobs.core.location_tags import (
    normalize_country_key,
    normalize_location,
    normalize_locations,
    picker_cities_for_country,
    sync_company_location_fields,
)
from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.catalog.repo import load_country_catalog


def list_company_locations(
    country_key: str | None = None,
    *,
    for_picker: bool = False,
) -> list[dict]:
    keyed: dict[str, dict] = {}
    filter_country = (
        normalize_country_key(country_key)
        if country_key and country_key != "all"
        else ""
    )

    def add(country: str, city: str) -> None:
        loc = normalize_location(country, city)
        if not loc:
            return
        if filter_country and not for_picker:
            if normalize_country_key(loc["country"]) != filter_country:
                return
        keyed.setdefault(loc["key"], loc)

    if for_picker:
        for key in SUPPORTED_COUNTRIES:
            for city in picker_cities_for_country(key):
                add(key, city)

    country_keys = (
        [filter_country]
        if filter_country
        else sorted(SUPPORTED_COUNTRIES)
    )
    for key in country_keys:
        data = load_country_catalog(key)
        if not data:
            continue
        for company in data.get("companies") or []:
            sync_company_location_fields(company, catalog_country=key)
            locations = normalize_locations(
                company.get("locations"),
                catalog_country=key,
                legacy_cities=company.get("cities") if isinstance(company.get("cities"), list) else None,
                legacy_city=company.get("city", ""),
            )
            for loc in locations:
                add(loc["country"], loc["city"])

    return sorted(keyed.values(), key=lambda loc: (loc["country_label"], loc["city"].casefold()))
