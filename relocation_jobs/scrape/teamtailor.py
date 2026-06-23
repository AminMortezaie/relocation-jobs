"""TeamTailor job board scraper."""

from __future__ import annotations

from bs4 import BeautifulSoup

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.http import requests
from relocation_jobs.scrape.ipc import report_activity
from relocation_jobs.scrape.listing import (
    collect_listing_job_links,
    listing_candidates_to_jobs,
    listing_job,
)
from relocation_jobs.scrape.relevance import is_relevant


def teamtailor_board_url(api_key_or_url: str, careers_url: str) -> str:
    if (api_key_or_url or "").startswith("http"):
        return api_key_or_url.rstrip("/")
    board = (careers_url or "").rstrip("/")
    if ".teamtailor.com" in board and not board.endswith("/jobs"):
        return f"{board.split('?')[0]}/jobs" if "/jobs" not in board else board.split("?")[0]
    return board


def scrape_teamtailor_html_board(
    board_url: str,
    *,
    relevant_only: bool = True,
    activity_reporter=None,
    listing_link_collector=collect_listing_job_links,
    candidates_to_jobs=listing_candidates_to_jobs,
) -> list[dict]:
    """TeamTailor career sites paginate with ?page=2 — not a real job posting."""
    reporter = activity_reporter or report_activity
    board = teamtailor_board_url(board_url, board_url)
    if not board.endswith("/jobs"):
        board = f"{board.rstrip('/')}/jobs"

    merged: dict[str, str] = {}
    page = 1
    while page <= 25:
        page_url = board if page == 1 else f"{board}?page={page}"
        if page > 1:
            reporter(f"Loading TeamTailor page {page}…")
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            if page == 1:
                print(f"    TeamTailor HTML error ({page_url}): {e}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        batch = listing_link_collector(soup, board)
        new_urls = [u for u in batch if u not in merged]
        if not new_urls:
            break
        for url in new_urls:
            merged[url] = batch[url]
        page += 1

    if not merged:
        return []
    jobs = candidates_to_jobs(merged, relevant_only=relevant_only)
    if jobs:
        print(f"    TeamTailor HTML board: {len(jobs)} role(s) across {page - 1} page(s)")
    return jobs


def teamtailor_location_map(included: list[dict] | None) -> dict[str, str]:
    loc_by_id: dict[str, str] = {}
    for item in included or []:
        if item.get("type") != "locations":
            continue
        attrs = item.get("attributes") or {}
        loc_by_id[item["id"]] = ", ".join(
            dict.fromkeys(
                p for p in (
                    (attrs.get("city") or "").strip(),
                    (attrs.get("country") or "").strip(),
                    (attrs.get("name") or "").strip(),
                ) if p
            )
        )
    return loc_by_id


def teamtailor_listing_jobs_from_feed(
    jobs: list[dict],
    included: list[dict] | None,
    careers_url: str,
    *,
    relevant_only: bool,
    location_mapper=teamtailor_location_map,
) -> list[dict]:
    loc_by_id = location_mapper(included)
    out: list[dict] = []
    for j in jobs:
        title = (j.get("attributes") or {}).get("title", "")
        if relevant_only and not is_relevant(title):
            continue
        loc_refs = (
            (j.get("relationships") or {}).get("locations") or {}
        ).get("data") or []
        locs = [
            loc_by_id[ref["id"]]
            for ref in loc_refs
            if ref.get("id") and loc_by_id.get(ref["id"])
        ]
        out.append(listing_job(
            title,
            j.get("links", {}).get("careersite-job-url", careers_url),
            location=locs[0] if len(locs) == 1 else None,
            locations=locs or None,
        ))
    return out


def fetch_teamtailor_jobs(api_key: str) -> tuple[list[dict], list[dict]]:
    """Teamtailor public job feed via Authorization token + pagination."""
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
                r = requests.get(url, headers=hdrs, timeout=15)
                if r.status_code == 406 and version != "20161108":
                    break
                r.raise_for_status()
                data = r.json()
                jobs.extend(data.get("data") or [])
                included.extend(data.get("included") or [])
                url = (data.get("links") or {}).get("next")
            if jobs:
                return jobs, included
        except Exception:
            continue

    try:
        r = requests.get(
            f"https://api.teamtailor.com/v1/jobs?api_key={api_key}&page[size]=30&filter[feed]=public",
            headers={**HEADERS, "X-Api-Version": "20210218"},
            timeout=15,
        )
        if r.ok:
            data = r.json()
            return list(data.get("data") or []), list(data.get("included") or [])
    except Exception:
        pass
    return [], []


def scrape_teamtailor(
    api_key_or_url: str,
    careers_url: str,
    *,
    relevant_only: bool = True,
    playwright_fallback=None,
    activity_reporter=None,
    listing_link_collector=None,
    candidates_to_jobs=None,
) -> list[dict]:
    """
    ats_url stores the API key when known, otherwise the board URL.
    Prefer the REST API; otherwise paginate the public HTML board.
    """
    from relocation_jobs.scrape.generic import scrape_with_playwright

    key = api_key_or_url if api_key_or_url and not api_key_or_url.startswith("http") else ""
    board_url = teamtailor_board_url(api_key_or_url, careers_url)

    if key:
        jobs, included = fetch_teamtailor_jobs(key)
        if jobs:
            out = teamtailor_listing_jobs_from_feed(
                jobs, included, careers_url, relevant_only=relevant_only,
            )
            if out:
                return out

    jobs = scrape_teamtailor_html_board(
        board_url,
        relevant_only=relevant_only,
        activity_reporter=activity_reporter,
        listing_link_collector=listing_link_collector,
        candidates_to_jobs=candidates_to_jobs,
    )
    if jobs:
        return jobs
    fallback = playwright_fallback or scrape_with_playwright
    return fallback(careers_url)
