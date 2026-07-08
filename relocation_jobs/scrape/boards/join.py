from __future__ import annotations

import json
import re

from relocation_jobs.core.ats_detection import HEADERS, _detect_join_from_url
from relocation_jobs.scrape.listing import listing_job


def parse_join_next_data(html: str) -> tuple[str | None, int | None, list[dict]]:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        return None, None, []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None, None, []
    state = data.get("props", {}).get("pageProps", {}).get("initialState", {})
    company = state.get("company") or {}
    jobs_block = state.get("jobs") or {}
    return (
        company.get("domain"),
        company.get("id"),
        list(jobs_block.get("items") or []),
    )


def join_jobs_from_items(items: list[dict], slug: str) -> list[dict]:
    base = f"https://join.com/companies/{slug}"
    jobs: list[dict] = []
    seen: set[str] = set()
    for item in items:
        title = (item.get("title") or "").strip()
        id_param = (item.get("idParam") or "").strip()
        if not title or not id_param:
            continue
        url = f"{base}/{id_param}"
        if url in seen:
            continue
        seen.add(url)
        jobs.append(listing_job(title, url))
    return jobs


async def fetch_join_board(client, board_url: str, company: dict) -> list[dict]:
    source = board_url or (company.get("careers_url") or "")
    detected = _detect_join_from_url(source)
    if not detected[1]:
        return []
    page_url = detected[1]
    slug_match = re.search(r"join\.com/companies/([a-zA-Z0-9_-]+)", page_url, re.I)
    slug = slug_match.group(1) if slug_match else page_url.rstrip("/").split("/")[-1]
    response = await client.get(page_url, headers=HEADERS, timeout=15.0)
    response.raise_for_status()
    slug_from_page, company_id, items = parse_join_next_data(response.text)
    if slug_from_page:
        slug = slug_from_page
    if company_id:
        try:
            api_response = await client.get(
                f"https://join.com/api/public/companies/{company_id}/jobs",
                headers={**HEADERS, "Accept": "application/json"},
                params={"page": 1, "pageSize": 50},
                timeout=15.0,
            )
            api_response.raise_for_status()
            data = api_response.json()
            api_items = list(data.get("items") or [])
        except Exception:
            api_items = []
        if api_items:
            items = api_items
    return join_jobs_from_items(items, slug)
