from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.dom_listing import (
    collect_listing_job_links,
    listing_candidates_to_jobs,
)
from relocation_jobs.scrape.listing import listing_job
from relocation_jobs.scrape.playwright_board import scrape_board_with_playwright


def teamtailor_board_url(api_key_or_url: str, careers_url: str) -> str:
    if (api_key_or_url or "").startswith("http"):
        return api_key_or_url.rstrip("/")
    board = (careers_url or "").rstrip("/")
    if ".teamtailor.com" in board and not board.endswith("/jobs"):
        return f"{board.split('?')[0]}/jobs" if "/jobs" not in board else board.split("?")[0]
    return board


def teamtailor_location_map(included: list[dict] | None) -> dict[str, str]:
    loc_by_id: dict[str, str] = {}
    for item in included or []:
        if item.get("type") != "locations":
            continue
        attrs = item.get("attributes") or {}
        loc_by_id[item["id"]] = ", ".join(
            dict.fromkeys(
                part for part in (
                    (attrs.get("city") or "").strip(),
                    (attrs.get("country") or "").strip(),
                    (attrs.get("name") or "").strip(),
                ) if part
            )
        )
    return loc_by_id


def teamtailor_jobs_from_feed(
    jobs: list[dict],
    included: list[dict] | None,
    careers_url: str,
) -> list[dict]:
    loc_by_id = teamtailor_location_map(included)
    out: list[dict] = []
    for row in jobs:
        title = ((row.get("attributes") or {}).get("title") or "").strip()
        if not title:
            continue
        loc_refs = ((row.get("relationships") or {}).get("locations") or {}).get("data") or []
        locs = [
            loc_by_id[ref["id"]]
            for ref in loc_refs
            if ref.get("id") and loc_by_id.get(ref["id"])
        ]
        out.append(
            listing_job(
                title,
                row.get("links", {}).get("careersite-job-url", careers_url),
                location=locs[0] if len(locs) == 1 else None,
                locations=locs or None,
            )
        )
    return out


def fetch_teamtailor_api_jobs(api_key: str) -> tuple[list[dict], list[dict]]:
    headers_base = {
        **HEADERS,
        "Authorization": f"Token token={api_key}",
        "Accept": "application/vnd.api+json",
    }
    for version in ("20240404", "20210218", "20161108"):
        jobs: list[dict] = []
        included: list[dict] = []
        url = (
            "https://api.teamtailor.com/v1/jobs"
            "?include=department,locations&page[size]=30&filter[feed]=public"
        )
        hdrs = {**headers_base, "X-Api-Version": version}
        try:
            while url:
                response = requests.get(url, headers=hdrs, timeout=15)
                if response.status_code == 406 and version != "20161108":
                    break
                response.raise_for_status()
                data = response.json()
                jobs.extend(data.get("data") or [])
                included.extend(data.get("included") or [])
                url = (data.get("links") or {}).get("next")
            if jobs:
                return jobs, included
        except Exception:
            continue
    try:
        response = requests.get(
            f"https://api.teamtailor.com/v1/jobs?api_key={api_key}&page[size]=30&filter[feed]=public",
            headers={**HEADERS, "X-Api-Version": "20210218"},
            timeout=15,
        )
        if response.ok:
            data = response.json()
            return list(data.get("data") or []), list(data.get("included") or [])
    except Exception:
        pass
    return [], []


def fetch_teamtailor_html_board(board_url: str) -> list[dict]:
    board = teamtailor_board_url(board_url, board_url)
    if not board.endswith("/jobs"):
        board = f"{board.rstrip('/')}/jobs"
    merged: dict[str, str] = {}
    page = 1
    while page <= 25:
        page_url = board if page == 1 else f"{board}?page={page}"
        try:
            response = requests.get(page_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
        except Exception:
            if page == 1:
                return []
            break
        soup = BeautifulSoup(response.text, "html.parser")
        batch = collect_listing_job_links(soup, board)
        new_urls = [url for url in batch if url not in merged]
        if not new_urls:
            break
        for url in new_urls:
            merged[url] = batch[url]
        page += 1
    if not merged:
        return []
    return listing_candidates_to_jobs(merged, relevant_only=False)


def fetch_teamtailor_board_sync(board_url: str, careers_url: str) -> list[dict]:
    key = board_url if board_url and not board_url.startswith("http") else ""
    if key:
        jobs, included = fetch_teamtailor_api_jobs(key)
        if jobs:
            out = teamtailor_jobs_from_feed(jobs, included, careers_url)
            if out:
                return out
    jobs = fetch_teamtailor_html_board(teamtailor_board_url(board_url, careers_url))
    if jobs:
        return jobs
    return scrape_board_with_playwright(careers_url or board_url)


async def fetch_teamtailor_board(client, board_url: str, company: dict) -> list[dict]:
    careers_url = (company.get("careers_url") or board_url).strip()
    return await run_sync(fetch_teamtailor_board_sync, board_url, careers_url)
