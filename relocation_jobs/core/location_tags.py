"""Country + city location tags for companies."""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from relocation_jobs.core.paths import data_dir, ensure_data_dir

SUGGESTED_CITIES: dict[str, tuple[str, ...]] = {
    "germany": (
        "Berlin", "Munich", "Hamburg", "Frankfurt", "Frankfurt am Main", "Cologne", "Düsseldorf",
        "Stuttgart", "Leipzig", "Dresden", "Nuremberg", "Hanover", "Bonn",
    ),
    "netherlands": (
        "Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven",
        "Haarlem", "Tilburg", "Groningen",
    ),
    "uk": (
        "London", "Manchester", "Birmingham", "Edinburgh", "Bristol",
        "Leeds", "Cambridge", "Glasgow",
    ),
    "portugal": (
        "Lisbon", "Porto", "Braga", "Coimbra", "Faro",
    ),
}

_custom_cities_lock = threading.Lock()
_custom_cities_cache: dict[str, list[str]] | None = None
_custom_countries_lock = threading.Lock()
_custom_countries_cache: dict[str, str] | None = None
_country_labels_cache: dict[str, str] | None = None
_country_suffix_labels_cache: tuple[str, ...] | None = None


def custom_cities_path() -> Path:
    return data_dir() / "custom_cities.json"


def custom_countries_path() -> Path:
    return data_dir() / "custom_countries.json"


def _invalidate_custom_cities_cache() -> None:
    global _custom_cities_cache
    _custom_cities_cache = None


def _invalidate_custom_countries_cache() -> None:
    global _custom_countries_cache, _country_labels_cache, _country_suffix_labels_cache
    _custom_countries_cache = None
    _country_labels_cache = None
    _country_suffix_labels_cache = None


def invalidate_country_labels_cache() -> None:
    global _country_labels_cache, _country_suffix_labels_cache
    _country_labels_cache = None
    _country_suffix_labels_cache = None


def load_custom_countries(*, use_cache: bool = True) -> dict[str, str]:
    global _custom_countries_cache
    if use_cache and _custom_countries_cache is not None:
        return _custom_countries_cache

    from relocation_jobs.catalog.custom_countries import load_country_labels_store

    parsed = load_country_labels_store()
    if use_cache:
        _custom_countries_cache = parsed
    return parsed


def save_custom_countries(data: dict[str, str]) -> None:
    from relocation_jobs.catalog.custom_countries import save_country_labels_store

    save_country_labels_store(data)
    _invalidate_custom_countries_cache()


def all_country_labels() -> dict[str, str]:
    global _country_labels_cache
    if _country_labels_cache is not None:
        return _country_labels_cache

    from relocation_jobs.catalog.custom_countries import list_catalog_country_keys

    merged = dict(load_custom_countries())
    for key in list_catalog_country_keys():
        if key not in merged:
            merged[key] = key.replace("-", " ").title()
    _country_labels_cache = merged
    return merged


def supported_country_keys() -> frozenset[str]:
    return frozenset(all_country_labels().keys())


def normalize_country_slug(label: str) -> str:
    s = (label or "").strip()
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def add_custom_country(label: str) -> dict:
    country_label_text = (label or "").strip()
    if not country_label_text:
        raise ValueError("Country name is required")

    country_key = normalize_country_slug(country_label_text)
    if not country_key:
        raise ValueError("Invalid country name")

    with _custom_countries_lock:
        data = load_custom_countries()
        for key, existing in data.items():
            if key == country_key or existing.casefold() == country_label_text.casefold():
                return {"id": key, "label": existing}
        from relocation_jobs.catalog.custom_countries import upsert_custom_country

        upsert_custom_country(country_key, country_label_text)
        _invalidate_custom_countries_cache()

    return {"id": country_key, "label": country_label_text}


def remove_custom_country(country_key: str) -> bool:
    key = normalize_country_key(country_key)
    if not key:
        raise ValueError("Country is required")

    from relocation_jobs.catalog.custom_countries import remove_custom_country as remove_country_label

    with _custom_countries_lock:
        removed_label = remove_country_label(key)
        cities = load_custom_cities(use_cache=False)
        if key in cities:
            del cities[key]
            save_custom_cities(cities)
        _invalidate_custom_countries_cache()

    return removed_label


def ensure_country_key(country_key: str) -> str:
    key = normalize_country_key(country_key)
    if not key:
        raise ValueError("Country is required")
    if key in supported_country_keys():
        return key
    add_custom_country(key.replace("-", " ").title())
    return key


def load_custom_cities(*, use_cache: bool = True) -> dict[str, list[str]]:
    """Return user-added picker cities keyed by country."""
    global _custom_cities_cache
    if use_cache and _custom_cities_cache is not None:
        return _custom_cities_cache

    path = custom_cities_path()
    raw: object = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}

    parsed: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for country, cities in raw.items():
            country_key = normalize_country_key(str(country))
            if country_key not in supported_country_keys() or not isinstance(cities, list):
                continue
            clean: list[str] = []
            seen: set[str] = set()
            for city in cities:
                if not isinstance(city, str):
                    continue
                label = city.strip()
                if not label:
                    continue
                city_key = normalize_city_key(label)
                if city_key in seen:
                    continue
                seen.add(city_key)
                clean.append(label)
            if clean:
                parsed[country_key] = clean

    if use_cache:
        _custom_cities_cache = parsed
    return parsed


def save_custom_cities(data: dict[str, list[str]]) -> None:
    ensure_data_dir()
    ordered = {
        key: data[key]
        for key in sorted(data)
        if key in supported_country_keys() and data[key]
    }
    custom_cities_path().write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _invalidate_custom_cities_cache()


def picker_cities_for_country(country: str) -> tuple[str, ...]:
    """Built-in suggested cities plus user-added picker cities."""
    country_key = normalize_country_key(country)
    if country_key not in supported_country_keys():
        return ()

    merged: list[str] = []
    seen: set[str] = set()
    for city in SUGGESTED_CITIES.get(country_key, ()):
        city_key = normalize_city_key(city)
        if city_key in seen:
            continue
        seen.add(city_key)
        merged.append(city)
    for city in load_custom_cities().get(country_key, []):
        city_key = normalize_city_key(city)
        if city_key in seen:
            continue
        seen.add(city_key)
        merged.append(city)
    return tuple(merged)


def add_custom_city(country: str, city: str) -> dict:
    """Persist a custom picker city and return the normalized location."""
    loc = normalize_location(country, city)
    if not loc:
        raise ValueError("Invalid country or city")

    country_key = loc["country"]
    city_label = loc["city"]
    city_key = normalize_city_key(city_label)

    with _custom_cities_lock:
        data = load_custom_cities()
        existing_custom = data.get(country_key, [])

        for existing in SUGGESTED_CITIES.get(country_key, ()):
            if city_match_keys(existing) & city_match_keys(city_label):
                return normalize_location(country_key, existing) or loc

        for existing in existing_custom:
            if city_match_keys(existing) & city_match_keys(city_label):
                return normalize_location(country_key, existing) or loc

        data[country_key] = [*existing_custom, city_label]
        save_custom_cities(data)

    return loc


def normalize_country_key(country: str) -> str:
    return (country or "").strip().lower()


def normalize_city_key(city: str) -> str:
    s = (city or "").strip().casefold()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def country_label(country: str) -> str:
    key = normalize_country_key(country)
    return all_country_labels().get(key, key.title() if key else "")


def location_key(country: str, city: str) -> str:
    return f"{normalize_country_key(country)}:{normalize_city_key(city)}"


def parse_location_filter(raw: str) -> tuple[str | None, str | None]:
    value = (raw or "").strip()
    if not value:
        return None, None
    if ":" in value:
        country, city = value.split(":", 1)
        country = normalize_country_key(country)
        city = (city or "").strip()
        return (country, city) if country and city else (None, None)
    return None, value


def format_location_display(country: str, city: str) -> str:
    city = (city or "").strip()
    if not city:
        return ""
    label = country_label(country)
    return f"{city} ({label})" if label else city


def _short_listing_location_label(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if "," in raw:
        return raw.split(",", 1)[0].strip()
    return raw


def format_job_location_label(job: dict) -> str:
    """City/location label from a scraped job listing (not company office tags)."""
    loc = (job.get("location") or "").strip()
    if loc:
        return _short_listing_location_label(loc)

    locations = job.get("locations")
    if isinstance(locations, list):
        labels: list[str] = []
        seen: set[str] = set()
        for item in locations:
            if isinstance(item, str):
                label = _short_listing_location_label(item)
            elif isinstance(item, dict):
                label = (
                    (item.get("city") or item.get("name") or item.get("label") or "")
                    .strip()
                )
                if not label and item.get("country"):
                    label = format_location_display(
                        str(item.get("country") or ""),
                        str(item.get("city") or item.get("name") or ""),
                    )
            else:
                label = ""
            if not label:
                continue
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
        return ", ".join(labels)

    if isinstance(locations, dict):
        city = (locations.get("city") or locations.get("name") or "").strip()
        if city:
            return city
        full = (locations.get("fullLocation") or locations.get("full_location") or "").strip()
        if full:
            return _short_listing_location_label(full)

    return ""


def job_location_fields(job: dict) -> dict:
    """Listing location fields preserved for API responses."""
    fields: dict = {}
    loc = (job.get("location") or "").strip()
    if loc:
        fields["location"] = loc
    locations = job.get("locations")
    if locations:
        fields["locations"] = locations
    label = format_job_location_label(job)
    if label:
        fields["job_city"] = label
    return fields


def _sorted_country_suffix_labels() -> tuple[str, ...]:
    global _country_suffix_labels_cache
    if _country_suffix_labels_cache is None:
        _country_suffix_labels_cache = tuple(
            sorted(all_country_labels().values(), key=len, reverse=True)
        )
    return _country_suffix_labels_cache


def _strip_country_suffix(city: str) -> str:
    stripped = (city or "").strip()
    if not stripped:
        return stripped
    changed = True
    while changed:
        changed = False
        for label in _sorted_country_suffix_labels():
            suffix = f" ({label})"
            if stripped.casefold().endswith(suffix.casefold()):
                stripped = stripped[: -len(suffix)].strip()
                changed = True
    return stripped or city


def _legacy_city_parts(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    if " · " in text:
        return [part.strip() for part in text.split(" · ") if part.strip()]
    return [text]


def normalize_location(country: str, city: str) -> dict | None:
    country_key = normalize_country_key(country)
    city_label = _strip_country_suffix((city or "").strip())
    if not country_key or country_key not in supported_country_keys() or not city_label:
        return None
    return {
        "country": country_key,
        "city": city_label,
        "country_label": country_label(country_key),
        "key": location_key(country_key, city_label),
        "label": format_location_display(country_key, city_label),
    }


def normalize_locations(
    raw_locations: list | None,
    *,
    catalog_country: str = "",
    legacy_cities: list[str] | None = None,
    legacy_city: str = "",
) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def add(country: str, city: str) -> None:
        loc = normalize_location(country, city)
        if not loc:
            return
        country_key = loc["country"]
        incoming_keys = city_match_keys(loc["city"])
        for existing in out:
            if existing["country"] != country_key:
                continue
            if city_match_keys(existing["city"]) & incoming_keys:
                return
        if loc["key"] in seen:
            return
        seen.add(loc["key"])
        out.append(loc)

    if isinstance(raw_locations, list):
        for item in raw_locations:
            if isinstance(item, dict):
                add(item.get("country", ""), item.get("city", ""))
            elif isinstance(item, str) and ":" in item:
                country, city = item.split(":", 1)
                add(country, city)

    if out:
        return sorted(out, key=lambda loc: (loc["country_label"], loc["city"].casefold()))

    catalog = normalize_country_key(catalog_country)
    if isinstance(legacy_cities, list):
        for city in legacy_cities:
            for part in _legacy_city_parts(str(city)):
                add(catalog or "", part)
        if out:
            return out

    single = (legacy_city or "").strip()
    if single:
        for part in _legacy_city_parts(single):
            add(catalog or "", part)
    return sorted(out, key=lambda loc: (loc["country_label"], loc["city"].casefold()))


def sync_company_location_fields(company: dict, *, catalog_country: str = "") -> None:
    locations = normalize_locations(
        company.get("locations"),
        catalog_country=catalog_country,
        legacy_cities=company.get("cities") if isinstance(company.get("cities"), list) else None,
        legacy_city=company.get("city", ""),
    )
    company["locations"] = locations
    company["cities"] = [loc["city"] for loc in locations]
    company["city"] = " · ".join(
        format_location_display(loc["country"], loc["city"]) for loc in locations
    )


def city_matches(company_city: str, filter_city: str) -> bool:
    if not (filter_city or "").strip():
        return True
    return bool(city_match_keys(company_city) & city_match_keys(filter_city))


def company_matches_location_filter(
    company: dict,
    filter_location: str,
    *,
    catalog_country: str = "",
) -> bool:
    filter_country, filter_city = parse_location_filter(filter_location)
    if not filter_country and not filter_city:
        return True
    locations = normalize_locations(
        company.get("locations"),
        catalog_country=catalog_country,
        legacy_cities=company.get("cities") if isinstance(company.get("cities"), list) else None,
        legacy_city=company.get("city", ""),
    )
    for loc in locations:
        if filter_country and normalize_country_key(loc["country"]) != filter_country:
            continue
        if filter_city and not city_matches(loc["city"], filter_city):
            continue
        return True
    return False


def company_visible_for_country_filter(
    company: dict,
    filter_country: str,
    *,
    catalog_country: str,
) -> bool:
    if not filter_country or filter_country == "all":
        return True
    if normalize_country_key(catalog_country) == normalize_country_key(filter_country):
        return True
    locations = normalize_locations(
        company.get("locations"),
        catalog_country=catalog_country,
        legacy_cities=company.get("cities") if isinstance(company.get("cities"), list) else None,
        legacy_city=company.get("city", ""),
    )
    return any(
        normalize_country_key(loc["country"]) == normalize_country_key(filter_country)
        for loc in locations
    )


def supported_country_keys_for_matching() -> frozenset[str]:
    return supported_country_keys()

_COUNTRY_TEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "germany": ("germany", "deutschland", "german", "de"),
    "netherlands": ("netherlands", "holland", "dutch", "nl", "the netherlands"),
    "uk": (
        "uk", "u.k.", "united kingdom", "great britain", "britain",
        "england", "scotland", "wales", "northern ireland", "gb",
    ),
    "portugal": ("portugal", "portuguese", "pt"),
}

_CITY_TEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "düsseldorf": ("dusseldorf",),
    "the hague": ("den haag", "s-gravenhage", "'s-gravenhage", "hague"),
    "munich": ("münchen", "muenchen"),
    "cologne": ("köln", "koeln"),
    "nuremberg": ("nürnberg", "nuernberg"),
    "hanover": ("hannover",),
    "frankfurt": ("frankfurt am main", "frankfurt/main"),
    "frankfurt am main": ("frankfurt", "frankfurt/main"),
}


def city_match_keys(city: str) -> set[str]:
    """Normalized city keys treated as the same place (incl. aliases)."""
    key = normalize_city_key(city)
    if not key:
        return set()
    keys = {key}
    for alias in _CITY_TEXT_ALIASES.get(key, ()):
        keys.add(alias)
    for canonical, aliases in _CITY_TEXT_ALIASES.items():
        if key == canonical or key in aliases:
            keys.add(canonical)
            keys.update(aliases)
    return keys


_UNSUPPORTED_COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "usa": ("usa", "u.s.a.", "united states", "united states of america", "u.s."),
    "france": ("france", "french"),
    "india": ("india", "indian"),
    "poland": ("poland", "polish"),
    "spain": ("spain", "spanish"),
    "italy": ("italy", "italian"),
    "canada": ("canada", "canadian"),
    "australia": ("australia", "australian"),
    "ireland": ("ireland", "irish"),
    "sweden": ("sweden", "swedish"),
    "switzerland": ("switzerland", "swiss"),
    "austria": ("austria", "austrian"),
    "belgium": ("belgium", "belgian"),
    "singapore": ("singapore",),
    "israel": ("israel",),
    "japan": ("japan", "japanese"),
    "china": ("china", "chinese"),
    "brazil": ("brazil", "brazilian"),
    "mexico": ("mexico", "mexican"),
}

_REMOTE_ONLY_RE = re.compile(
    r"^(?:remote|hybrid|fully\s+remote|work\s+from\s+home|wfh"
    r"|anywhere|worldwide|global)(?:\s*[-–—|/]\s*)?$",
    re.I,
)

_US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})

_TRAILING_REGION_RE = re.compile(r",\s*([A-Za-z]{2})\s*$")

_INDIA_CITY_HINTS = frozenset({
    "bengaluru", "bangalore", "mumbai", "delhi", "hyderabad", "pune", "chennai",
    "gurgaon", "gurugram", "noida", "kolkata", "ahmedabad",
})


def _unsupported_country_key_from_text(text: str) -> str | None:
    hay = f" {text.casefold()} "
    for country_key, aliases in _UNSUPPORTED_COUNTRY_ALIASES.items():
        for alias in aliases:
            token = alias.casefold()
            if len(token) <= 2:
                if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", hay):
                    return country_key
            elif token in hay:
                return country_key
    return None


def company_expected_locations(
    company: dict,
    *,
    catalog_country: str = "",
) -> list[dict]:
    """Office tags we expect open roles to match."""
    return normalize_locations(
        company.get("locations"),
        catalog_country=catalog_country,
        legacy_cities=company.get("cities") if isinstance(company.get("cities"), list) else None,
        legacy_city=company.get("city", ""),
    )


def _format_location_piece(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts: list[str] = []
        for key in (
            "fullLocation", "full_location", "name", "city", "region",
            "state", "country", "countryName", "country_name", "label",
        ):
            piece = value.get(key)
            if isinstance(piece, str) and piece.strip():
                parts.append(piece.strip())
        return ", ".join(dict.fromkeys(parts))
    if isinstance(value, list):
        return " | ".join(p for p in (_format_location_piece(item) for item in value) if p)
    return str(value).strip()


def job_listing_location_texts(job: dict) -> list[str]:
    """Collect location hints from a scraped listing (no JD fetch)."""
    texts: list[str] = []
    seen: set[str] = set()

    def add(raw) -> None:
        text = _format_location_piece(raw)
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        texts.append(text)

    add(job.get("location"))
    locs = job.get("locations")
    if isinstance(locs, list):
        for item in locs:
            add(item)
    elif locs:
        add(locs)

    url = (job.get("url") or "").strip()
    if url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        for key in ("location", "locations", "city", "office", "geo", "loc"):
            for val in qs.get(key) or []:
                add(unquote(val))
        path = unquote(parsed.path or "")
        for match in re.finditer(
            r"/(?:locations?|offices?|cities?)/([^/?#]+)",
            path,
            re.I,
        ):
            add(match.group(1).replace("-", " ").replace("_", " "))

    title = (job.get("title") or "").strip()
    if title:
        for sep in (" – ", " — ", " - ", " | ", " / "):
            if sep in title:
                tail = title.rsplit(sep, 1)[-1].strip()
                if tail and tail.casefold() != title.casefold():
                    add(tail)
                break

    return texts


def _country_key_from_text(text: str) -> str | None:
    hay = f" {text.casefold()} "
    for country_key, aliases in _COUNTRY_TEXT_ALIASES.items():
        for alias in aliases:
            token = alias.casefold()
            if len(token) <= 2:
                if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", hay):
                    return country_key
            elif token in hay:
                return country_key
    return None


def _city_keys_from_text(text: str, *, country_key: str | None = None) -> set[str]:
    hay = text.casefold()
    found: set[str] = set()

    def consider(city_label: str) -> None:
        city_key = normalize_city_key(city_label)
        if not city_key:
            return
        aliases = _CITY_TEXT_ALIASES.get(city_key, ())
        variants = (city_key, *aliases)
        if any(variant and variant in hay for variant in variants):
            found.update(city_match_keys(city_label))

    if country_key:
        for city_label in SUGGESTED_CITIES.get(country_key, ()):
            consider(city_label)
    else:
        for cities in SUGGESTED_CITIES.values():
            for city_label in cities:
                consider(city_label)
    return found


def _parse_listing_location(text: str) -> tuple[str | None, set[str], bool]:
    """
    Parse one listing location string.

    Returns (country_key, city_keys, is_remote_only).
    """
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return None, set(), False
    if _REMOTE_ONLY_RE.match(cleaned):
        return None, set(), True

    unsupported = _unsupported_country_key_from_text(cleaned)
    if unsupported:
        return f"unsupported:{unsupported}", set(), False

    region_match = _TRAILING_REGION_RE.search(cleaned)
    if region_match:
        code = region_match.group(1).upper()
        city_part = cleaned[:region_match.start()].strip()
        city_keys = _city_keys_from_text(city_part, country_key=None)
        city_hint = city_part.casefold()
        if code == "IN" and (
            city_keys
            or any(hint in city_hint for hint in _INDIA_CITY_HINTS)
        ):
            return "unsupported:india", city_keys, False
        if code in _US_STATE_CODES:
            return "unsupported:usa", city_keys, False

    country_key = _country_key_from_text(cleaned)
    city_keys = _city_keys_from_text(cleaned, country_key=country_key)
    return country_key, city_keys, False


def _text_matches_expected_offices(text: str, expected: list[dict]) -> bool:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return True
    if _REMOTE_ONLY_RE.match(cleaned):
        return True

    country_key, city_keys, is_remote_only = _parse_listing_location(cleaned)
    if is_remote_only:
        return True
    if country_key and country_key.startswith("unsupported:"):
        return False
    if country_key and country_key not in supported_country_keys():
        return False

    supported_countries = {
        normalize_country_key(loc["country"]) for loc in expected
    }
    if country_key and country_key not in supported_countries:
        return False

    if city_keys:
        return any(
            match_key in city_keys
            for loc in expected
            for match_key in city_match_keys(loc["city"])
        )

    hay = cleaned.casefold()
    for loc in expected:
        for match_key in city_match_keys(loc["city"]):
            if match_key in hay:
                return True
    return False


def _looks_like_location_text(text: str) -> bool:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return False
    if _REMOTE_ONLY_RE.match(cleaned):
        return True
    if _unsupported_country_key_from_text(cleaned):
        return True
    if _country_key_from_text(cleaned):
        return True
    if _city_keys_from_text(cleaned, country_key=None):
        return True
    if _TRAILING_REGION_RE.search(cleaned):
        return True
    if "," in cleaned:
        return True
    if "&" in cleaned:
        return False
    if re.search(
        r"\b(engineer|engineering|manager|analyst|intern|services|platform|payments?|fraud)\b",
        cleaned,
        re.I,
    ):
        return False
    tokens = cleaned.split()
    return len(tokens) == 1


def _listing_text_matches_expected_offices(text: str, expected: list[dict]) -> bool:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return True
    parts = re.split(r"\s+or\s+|\s*\|\s*", cleaned, flags=re.I)
    return any(
        _text_matches_expected_offices(part.strip(), expected)
        for part in parts
        if part.strip()
    )


def job_matches_expected_locations(
    job: dict,
    expected: list[dict],
) -> tuple[bool, str | None]:
    """
    Decide whether a scraped listing belongs on the board.

    Uses listing metadata only (location fields, URL, title suffix).
    Returns (include, skip_reason).
    """
    if not expected:
        return True, None

    texts = job_listing_location_texts(job)
    if not texts:
        return True, None

    supported_countries = {
        normalize_country_key(loc["country"]) for loc in expected
    }
    expected_by_country: dict[str, set[str]] = {}
    for loc in expected:
        country = normalize_country_key(loc["country"])
        for match_key in city_match_keys(loc["city"]):
            expected_by_country.setdefault(country, set()).add(match_key)

    saw_actionable = False
    explicit_mismatch = False
    remote_only = True
    unparsed_texts: list[str] = []

    for text in texts:
        country_key, city_keys, is_remote_only = _parse_listing_location(text)
        if is_remote_only:
            continue
        remote_only = False
        if not country_key and not city_keys:
            unparsed_texts.append(text)
            continue
        saw_actionable = True

        if country_key and country_key.startswith("unsupported:"):
            return False, f"unsupported country ({country_key.split(':', 1)[1]})"
        if country_key and country_key not in supported_country_keys():
            return False, f"unsupported country ({country_key})"
        if country_key and country_key not in supported_countries:
            return False, f"outside tagged countries ({country_key})"

        if country_key:
            expected_cities = expected_by_country.get(country_key, set())
            if city_keys:
                if city_keys & expected_cities:
                    return True, None
                explicit_mismatch = True
            else:
                return True, None
            continue

        if city_keys:
            if any(
                match_key in city_keys
                for loc in expected
                if normalize_country_key(loc["country"]) in supported_countries
                for match_key in city_match_keys(loc["city"])
            ):
                return True, None
            explicit_mismatch = True

    if remote_only and not saw_actionable and not unparsed_texts:
        return False, "remote only"
    if explicit_mismatch:
        return False, "city mismatch"
    if not saw_actionable:
        if unparsed_texts:
            actionable = [text for text in unparsed_texts if _looks_like_location_text(text)]
            if not actionable:
                return True, None
            if any(
                _listing_text_matches_expected_offices(text, expected)
                for text in actionable
            ):
                return True, None
            return False, "location mismatch"
        return True, None
    return False, "location mismatch"


def filter_jobs_by_expected_locations(
    jobs: list[dict],
    company: dict,
    *,
    catalog_country: str = "",
) -> tuple[list[dict], list[dict]]:
    """Split jobs into included vs excluded by company office tags."""
    expected = company_expected_locations(company, catalog_country=catalog_country)
    if not expected:
        return jobs, []

    included: list[dict] = []
    excluded: list[dict] = []
    for job in jobs:
        ok, reason = job_matches_expected_locations(job, expected)
        if ok:
            included.append(job)
        else:
            excluded.append({**job, "location_filter_reason": reason})
    return included, excluded


def job_fails_office_location_gate(
    job: dict,
    company: dict,
    *,
    catalog_country: str = "",
) -> tuple[bool, str | None]:
    """True when the company has office tags and the listing is outside them."""
    expected = company_expected_locations(company, catalog_country=catalog_country)
    if not expected:
        return False, None
    ok, reason = job_matches_expected_locations(job, expected)
    if ok:
        return False, None
    return True, reason


def tag_wrong_location_jobs(
    jobs: list[dict],
    company: dict,
    *,
    catalog_country: str = "",
    tagged_date: str | None = None,
) -> None:
    """Mark catalog jobs outside office tags as not_for_me with reason wrong_location."""
    expected = company_expected_locations(company, catalog_country=catalog_country)
    if not expected:
        return
    stamp = tagged_date or date.today().isoformat()
    for job in jobs:
        ok, _ = job_matches_expected_locations(job, expected)
        if ok:
            if job.get("not_for_me_reason") == "wrong_location":
                job.pop("not_for_me", None)
                job.pop("not_for_me_reason", None)
                job.pop("not_for_me_date", None)
            continue
        job["not_for_me"] = True
        job["not_for_me_reason"] = "wrong_location"
        job["not_for_me_date"] = job.get("not_for_me_date") or stamp
