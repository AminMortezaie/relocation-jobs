from __future__ import annotations

from relocation_jobs.core.location_tags import (
    normalize_country_key,
    normalize_location,
    normalize_locations,
    picker_cities_for_country,
)
from relocation_jobs.core.paths import supported_countries
from relocation_jobs.catalog.repo import load_company_location_sources
from relocation_jobs.catalog.serialize import parse_cities_json, parse_locations_json


def _add_locations_from_company_rows(rows: list[dict], add) -> None:
    for row in rows:
        catalog_country = row.get("country") or ""
        parsed = parse_locations_json(
            row.get("locations_json"),
            catalog_country=catalog_country,
        )
        if parsed:
            for loc in parsed:
                add(loc.country, loc.city)
            continue
        for loc in normalize_locations(
            None,
            catalog_country=catalog_country,
            legacy_cities=parse_cities_json(row.get("cities_json")),
            legacy_city=row.get("city") or "",
        ):
            add(loc["country"], loc["city"])


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
        for key in supported_countries():
            for city in picker_cities_for_country(key):
                add(key, city)

    country_keys = (
        [filter_country]
        if filter_country
        else sorted(supported_countries())
    )
    _add_locations_from_company_rows(
        load_company_location_sources(country_keys),
        add,
    )

    return sorted(keyed.values(), key=lambda loc: (loc["country_label"], loc["city"].casefold()))
