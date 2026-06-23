"""Join.com job board scraper."""

from __future__ import annotations

import json
import re

from relocation_jobs.core.ats_detection import HEADERS, _detect_join_from_url
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.relevance import is_relevant


def parse_join_next_data(html: str) -> tuple[str | None, int | None, list[dict]]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None, None, []
    try:
        data = json.loads(m.group(1))
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


def join_jobs_from_items(
    items: list[dict],
    slug: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    base = f"https://join.com/companies/{slug}"
    jobs: list[dict] = []
    seen: set[str] = set()
    for item in items:
        title = (item.get("title") or "").strip()
        id_param = (item.get("idParam") or "").strip()
        if not title or not id_param:
            continue
        if relevant_only and not is_relevant(title):
            continue
        url = f"{base}/{id_param}"
        if url in seen:
            continue
        seen.add(url)
        jobs.append({"title": title, "url": url})
    return jobs


def fetch_join_items_via_api(
    company_id: int,
    *,
    headers: dict | None = None,
) -> list[dict]:
    hdrs = headers or HEADERS
    items: list[dict] = []
    page = 1
    while page <= 20:
        try:
            r = requests.get(
                f"https://join.com/api/public/companies/{company_id}/jobs",
                headers={**hdrs, "Accept": "application/json"},
                params={"page": page, "pageSize": 100},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        batch = list(data.get("items") or [])
        if not batch:
            break
        items.extend(batch)
        pagination = data.get("pagination") or {}
        page_count = int(pagination.get("pageCount") or 1)
        if page >= page_count:
            break
        page += 1
    return items


def scrape_join(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Scrape join.com company boards via __NEXT_DATA__ and public jobs API."""
    detected = _detect_join_from_url(careers_url)
    if not detected[1]:
        return []
    board_url = detected[1]
    slug_m = re.search(r"join\.com/companies/([a-zA-Z0-9_-]+)", board_url, re.I)
    slug = slug_m.group(1) if slug_m else board_url.rstrip("/").split("/")[-1]

    try:
        r = requests.get(board_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    Join error ({board_url}): {e}")
        return []

    slug_from_page, company_id, items = parse_join_next_data(r.text)
    if slug_from_page:
        slug = slug_from_page

    if company_id:
        api_items = fetch_join_items_via_api(company_id)
        if api_items:
            items = api_items

    return join_jobs_from_items(items, slug, relevant_only=relevant_only)


async def scrape_join_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    detected = _detect_join_from_url(ats_url)
    if not detected[1]:
        return []
    board_url = detected[1]
    slug_m = re.search(r"join\.com/companies/([a-zA-Z0-9_-]+)", board_url, re.I)
    slug = slug_m.group(1) if slug_m else board_url.rstrip("/").split("/")[-1]

    try:
        r = await client.get(board_url, timeout=15.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Join error ({board_url}): {e}")
        return []

    slug_from_page, company_id, items = parse_join_next_data(r.text)
    if slug_from_page:
        slug = slug_from_page

    if company_id:
        api_items: list[dict] = []
        page = 1
        while page <= 20:
            try:
                api_r = await client.get(
                    f"https://join.com/api/public/companies/{company_id}/jobs",
                    headers={"Accept": "application/json"},
                    params={"page": page, "pageSize": 100},
                    timeout=15.0,
                )
                api_r.raise_for_status()
                data = api_r.json()
            except Exception:
                break
            batch = list(data.get("items") or [])
            if not batch:
                break
            api_items.extend(batch)
            pagination = data.get("pagination") or {}
            page_count = int(pagination.get("pageCount") or 1)
            if page >= page_count:
                break
            page += 1
        if api_items:
            items = api_items

    return join_jobs_from_items(items, slug, relevant_only=relevant_only)
