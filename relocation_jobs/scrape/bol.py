"""bol.com careers API scraper."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urljoin, urlparse

from relocation_jobs.core.ats_constants import BOL_CAREERS_API
from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.http import httpx, requests


def bol_doelgroep_from_url(careers_url: str) -> str | None:
    qs = parse_qs(urlparse(careers_url).query)
    vals = qs.get("doelgroep[]") or qs.get("doelgroep")
    return vals[0] if vals else None


def bol_search_payload(careers_url: str, *, size: int = 200) -> dict:
    doelgroep = bol_doelgroep_from_url(careers_url)
    if doelgroep:
        es_query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_all": {}},
                        {
                            "bool": {
                                "should": [
                                    {"bool": {"filter": [{"term": {"doelgroep": doelgroep}}]}}
                                ]
                            }
                        },
                    ]
                }
            },
            "sort": [{"_score": "desc"}],
            "from": 0,
            "size": size,
        }
    else:
        es_query = {
            "query": {"bool": {"must": [{"match_all": {}}]}},
            "sort": [{"_score": "desc"}],
            "from": 0,
            "size": size,
        }
    return {
        "body": json.dumps(es_query),
        "languages": ["nl", "en"],
        "preferred_language": "en",
    }


def jobs_from_bol_response(data: dict) -> list[dict]:
    hits = (data.get("results") or {}).get("hits", {}).get("hits", [])
    jobs: list[dict] = []
    for hit in hits:
        src = hit.get("_source") or {}
        title = (src.get("publicatienaam") or src.get("post_title") or "").strip()
        if not title:
            continue
        slug = (src.get("slug") or "").strip()
        if slug.startswith("/"):
            job_url = urljoin("https://careers.bol.com", slug)
        elif slug:
            job_url = slug
        else:
            job_url = "https://careers.bol.com/en/jobs/"
        jobs.append({"title": title, "url": job_url})
    return jobs


def scrape_bol(careers_url: str) -> list[dict]:
    """bol careers.bol.com uses a custom WP/Elasticsearch API, not boards.greenhouse.io."""
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": careers_url or "https://careers.bol.com/en/jobs/",
    }
    try:
        r = requests.post(
            BOL_CAREERS_API,
            json=bol_search_payload(careers_url),
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            print(f"    bol careers API error: {data}")
            return []
        return jobs_from_bol_response(data)
    except Exception as e:
        print(f"    bol careers error ({careers_url}): {e}")
        return []


async def scrape_bol_async(client: httpx.AsyncClient, careers_url: str) -> list[dict]:
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": careers_url or "https://careers.bol.com/en/jobs/",
    }
    try:
        r = await client.post(
            BOL_CAREERS_API,
            json=bol_search_payload(careers_url),
            headers=headers,
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            print(f"    bol careers API error: {data}")
            return []
        return jobs_from_bol_response(data)
    except Exception as e:
        print(f"    bol careers error ({careers_url}): {e}")
        return []
