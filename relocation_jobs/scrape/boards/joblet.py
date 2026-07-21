from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.listing import listing_job

DEFAULT_JOBLET_BOARD = "https://joblet.ai/jobs?employmentType=Remote"
DEFAULT_JOBLET_SEARCH = "https://joblet.ai/api/search"

_TAG_RE = re.compile(r"<[^>]+>")

_SEARCH_QUERIES = (
    "software engineer",
    "frontend",
    "full stack",
    "devops",
    "platform engineer",
    "data engineer",
    "machine learning",
    "typescript",
    "staff engineer",
    "principal engineer",
)

_REQUEST_HEADERS = {
    **HEADERS,
    "Accept": "application/json",
    "Origin": "https://joblet.ai",
    "Referer": DEFAULT_JOBLET_BOARD,
}


def joblet_board_url(board_url: str) -> str:
    raw = (board_url or "").strip()
    if not raw:
        return DEFAULT_JOBLET_BOARD
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if "joblet.ai" not in host:
        return DEFAULT_JOBLET_BOARD
    qs = parse_qs(parsed.query)
    if "employmentType" not in qs:
        qs["employmentType"] = ["Remote"]
    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path or "/jobs",
            "",
            urlencode(qs, doseq=True),
            "",
        )
    )


def _plain_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _employer_name(row: dict) -> str:
    company = row.get("company")
    if isinstance(company, dict):
        return (company.get("name") or "").strip()
    if isinstance(company, str):
        return company.strip()
    return ""


def _job_url(row: dict) -> str:
    slug = (row.get("slug") or row.get("url_slug") or "").strip()
    if slug:
        return f"https://joblet.ai/jobs/{slug.lstrip('/')}"
    return (row.get("applyUrl") or row.get("url") or "").strip()


def _is_remote_row(row: dict) -> bool:
    if row.get("isRemote") is True:
        return True
    types = row.get("employmentType") or []
    if isinstance(types, list) and any(str(t).strip().casefold() == "remote" for t in types):
        return True
    location = (row.get("location") or "").casefold()
    return "remote" in location


def parse_joblet_search_payload(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    rows = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    jobs: list[dict] = []
    for row in rows:
        if not isinstance(row, dict) or not _is_remote_row(row):
            continue
        title = (row.get("title") or "").strip()
        url = _job_url(row)
        employer = _employer_name(row)
        if not title or not url or not employer:
            continue
        location = (row.get("location") or "").strip() or "Remote"
        description = _plain_text(row.get("description") or "")
        jobs.append(
            listing_job(
                title,
                url,
                location=location,
                employer=employer,
                description_text=description or None,
            )
        )
    return jobs


def _search_url(query: str, *, page: int = 1) -> str:
    return (
        f"{DEFAULT_JOBLET_SEARCH}?"
        + urlencode({"q": query, "location": "Remote", "page": page})
    )


def fetch_joblet_board_sync(board_url: str) -> list[dict]:
    referer = joblet_board_url(board_url)
    headers = {**_REQUEST_HEADERS, "Referer": referer}
    by_url: dict[str, dict] = {}
    for query in _SEARCH_QUERIES:
        response = requests.get(_search_url(query), headers=headers, timeout=30)
        response.raise_for_status()
        for job in parse_joblet_search_payload(response.json()):
            by_url[job["url"]] = job
    return list(by_url.values())


async def fetch_joblet_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("ats_url") or company.get("careers_url") or "")
    return await run_sync(fetch_joblet_board_sync, url)
