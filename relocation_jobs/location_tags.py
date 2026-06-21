"""Country + city location tags for companies."""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from relocation_jobs.paths import data_dir, ensure_data_dir

COUNTRY_LABELS: dict[str, str] = {
    "germany": "Germany",
    "netherlands": "Netherlands",
    "uk": "United Kingdom",
    "portugal": "Portugal",
}

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


def custom_cities_path() -> Path:
    return data_dir() / "custom_cities.json"


def _invalidate_custom_cities_cache() -> None:
    global _custom_cities_cache
    _custom_cities_cache = None


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
            if country_key not in COUNTRY_LABELS or not isinstance(cities, list):
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
        if key in COUNTRY_LABELS and data[key]
    }
    custom_cities_path().write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _invalidate_custom_cities_cache()


def picker_cities_for_country(country: str) -> tuple[str, ...]:
    """Built-in suggested cities plus user-added picker cities."""
    country_key = normalize_country_key(country)
    if country_key not in COUNTRY_LABELS:
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
    return COUNTRY_LABELS.get(key, key.title() if key else "")


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


def normalize_location(country: str, city: str) -> dict | None:
    country_key = normalize_country_key(country)
    city_label = (city or "").strip()
    if not country_key or country_key not in COUNTRY_LABELS or not city_label:
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
        if not loc or loc["key"] in seen:
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
            add(catalog or "", city)
        if out:
            return out

    single = (legacy_city or "").strip()
    if single:
        if "," in single:
            for part in single.split(","):
                add(catalog or "", part.strip())
        else:
            add(catalog or "", single)
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


SUPPORTED_COUNTRY_KEYS = frozenset(COUNTRY_LABELS.keys())

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

    country_key = _country_key_from_text(cleaned)
    city_keys = _city_keys_from_text(cleaned, country_key=country_key)
    return country_key, city_keys, False


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

    for text in texts:
        country_key, city_keys, is_remote_only = _parse_listing_location(text)
        if is_remote_only:
            continue
        remote_only = False
        if not country_key and not city_keys:
            continue
        saw_actionable = True

        if country_key and country_key.startswith("unsupported:"):
            return False, f"unsupported country ({country_key.split(':', 1)[1]})"
        if country_key and country_key not in SUPPORTED_COUNTRY_KEYS:
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

    if remote_only and not saw_actionable:
        return False, "remote only"
    if explicit_mismatch:
        return False, "city mismatch"
    if not saw_actionable:
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
