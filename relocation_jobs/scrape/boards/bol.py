from __future__ import annotations

import json
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from relocation_jobs.core.ats_constants import BOL_CAREERS_API
from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.listing import listing_job


def bol_search_payload(careers_url: str, *, size: int = 200) -> dict:
    from urllib.parse import parse_qs

    qs = parse_qs(urlparse(careers_url).query)
    vals = qs.get("doelgroep[]") or qs.get("doelgroep")
    doelgroep = vals[0] if vals else None
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


def parse_bol_response(data: dict) -> list[dict]:
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
        jobs.append(listing_job(title, job_url))
    return jobs


async def fetch_bol_board(client, board_url: str, company: dict) -> list[dict]:
    careers_url = (company.get("careers_url") or board_url).strip()
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": careers_url or "https://careers.bol.com/en/jobs/",
    }
    response = await client.post(
        BOL_CAREERS_API,
        json=bol_search_payload(careers_url),
        headers=headers,
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        return []
    return parse_bol_response(data)
