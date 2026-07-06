from __future__ import annotations

import html as html_module
import re

import requests

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.listing import listing_job

_GREENHOUSE_JOB_URL_RE = re.compile(
    r"greenhouse\.io/(?:[^/]+/)?jobs/(\d+)",
    re.I,
)
_GREENHOUSE_BOARD_URL_RE = re.compile(
    r"greenhouse\.io/([^/]+)/jobs/",
    re.I,
)
_GREENHOUSE_EMBED_BOARD_RE = re.compile(
    r"greenhouse\.io/embed[^?]*\?(?:[^&]*&)*for=([a-z0-9_-]+)",
    re.I,
)
_GREENHOUSE_EMBED_TOKEN_RE = re.compile(r"token=(\d+)", re.I)
_GH_JID_RE = re.compile(r"(?:^|[?&])gh_jid=(\d+)", re.I)
_CUSTOM_JOB_ID_RE = re.compile(r"/(?:job|jobs|positions)/(\d+)(?:[/?#]|$)", re.I)
_BRANDED_GREENHOUSE_CAREERS = {
    "getyourguide.careers": "getyourguide",
}


def greenhouse_board_slug(ats_url: str) -> str:
    return ats_url.rstrip("/").split("/")[-1].split("?")[0]


def greenhouse_jobs_api_url(slug: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def greenhouse_job_detail_api_url(slug: str, job_id: str, *, eu: bool = False) -> str:
    host = "boards-api.eu.greenhouse.io" if eu else "boards-api.greenhouse.io"
    return f"https://{host}/v1/boards/{slug}/jobs/{job_id}"


def greenhouse_job_ids_from_url(url: str, *, board_slug: str = "") -> tuple[str, str] | None:
    text = (url or "").strip()
    if not text:
        return None
    embed_board = _GREENHOUSE_EMBED_BOARD_RE.search(text)
    embed_token = _GREENHOUSE_EMBED_TOKEN_RE.search(text)
    if embed_board and embed_token:
        return embed_board.group(1), embed_token.group(1)
    match = _GREENHOUSE_JOB_URL_RE.search(text)
    if match:
        job_id = match.group(1)
        board_match = _GREENHOUSE_BOARD_URL_RE.search(text)
        slug = board_match.group(1) if board_match else ""
        if slug and slug not in ("embed", "jobs"):
            return slug, job_id
    lowered = text.lower()
    for host, board in _BRANDED_GREENHOUSE_CAREERS.items():
        if host in lowered:
            branded = re.search(r"/jobs/(\d+)", text)
            if branded:
                return board, branded.group(1)
    slug_hint = (board_slug or "").strip()
    if slug_hint:
        gh_jid = _GH_JID_RE.search(text)
        if gh_jid:
            return slug_hint, gh_jid.group(1)
        path_job = _CUSTOM_JOB_ID_RE.search(text)
        if path_job:
            return slug_hint, path_job.group(1)
    return None


def greenhouse_job_detail(slug: str, job_id: str) -> tuple[str, str]:
    for eu in (False, True):
        api = greenhouse_job_detail_api_url(slug, job_id, eu=eu)
        try:
            response = requests.get(api, headers=HEADERS, timeout=10)
            if not response.ok:
                continue
            payload = response.json()
            raw = (payload.get("content") or "").strip()
            if not raw:
                continue
            location = ((payload.get("location") or {}).get("name") or "").strip()
            return html_module.unescape(raw), location
        except Exception:
            pass
    return "", ""


def greenhouse_job_content(slug: str, job_id: str) -> str:
    content, _location = greenhouse_job_detail(slug, job_id)
    return content


async def fetch_greenhouse_board(client, board_url: str, company: dict) -> list[dict]:
    slug = greenhouse_board_slug(board_url)
    if not slug or slug in ("embed", "jobs", ""):
        return []
    response = await client.get(
        greenhouse_jobs_api_url(slug),
        headers=HEADERS,
        timeout=10.0,
    )
    response.raise_for_status()
    jobs: list[dict] = []
    for row in response.json().get("jobs") or []:
        title = (row.get("title") or "").strip()
        url = (row.get("absolute_url") or "").strip()
        if not title or not url:
            continue
        location = (row.get("location") or {}).get("name")
        jobs.append(listing_job(title, url, location=location))
    return jobs
