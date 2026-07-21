from __future__ import annotations

from relocation_jobs.catalog.repo import get_company, upsert_company
from relocation_jobs.core.location_tags import (
    add_custom_country,
    normalize_country_key,
    supported_country_keys,
)
from relocation_jobs.scrape.merge import now_iso

AGGREGATOR_SEEDS: tuple[dict[str, str], ...] = (
    {
        "country_key": "remote-ok",
        "country_label": "Remote OK",
        "name": "Remote OK",
        "ats_type": "remoteok",
        "careers_url": "https://remoteok.com/api?tags=dev",
    },
    {
        "country_key": "uae",
        "country_label": "UAE",
        "name": "Remote DXB",
        "ats_type": "remotedxb",
        "careers_url": "https://www.remotedxb.com/rss",
    },
)


def _ensure_seed_country(country_key: str, country_label: str) -> str:
    key = normalize_country_key(country_key)
    if key not in supported_country_keys():
        add_custom_country(country_label)
    return key


def ensure_aggregator_seeds() -> list[dict]:
    created: list[dict] = []
    ts = now_iso()
    for seed in AGGREGATOR_SEEDS:
        country_key = _ensure_seed_country(seed["country_key"], seed["country_label"])
        name = seed["name"]
        if get_company(country_key, name) is not None:
            continue
        company = {
            "name": name,
            "city": "",
            "size": "",
            "careers_url": seed["careers_url"],
            "ats_type": seed["ats_type"],
            "ats_url": seed["careers_url"],
            "matching_jobs": [],
            "sources": ["aggregator"],
            "added": ts,
            "updated": ts,
        }
        upsert_company(country_key, company, updated=ts)
        created.append({"country": country_key, "company": name, "ats_type": seed["ats_type"]})
    return created
