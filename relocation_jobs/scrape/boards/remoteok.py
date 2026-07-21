from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlparse

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.listing import listing_job

_TAG_RE = re.compile(r"<[^>]+>")

DEFAULT_REMOTEOK_API = "https://remoteok.com/api?tags=dev"

_DEV_TAG_HINTS = frozenset({
    "dev",
    "engineering",
    "software",
    "engineer",
    "backend",
    "frontend",
    "fullstack",
    "full-stack",
    "devops",
    "sre",
    "golang",
    "python",
    "java",
    "javascript",
    "typescript",
    "kotlin",
    "rust",
    "api",
    "infra",
    "infrastructure",
    "platform",
})


def remoteok_api_url(board_url: str) -> str:
    raw = (board_url or "").strip() or DEFAULT_REMOTEOK_API
    parsed = urlparse(raw)
    if not parsed.scheme:
        return DEFAULT_REMOTEOK_API
    path = (parsed.path or "").rstrip("/")
    if path in ("", "/api"):
        query = parsed.query
        if query:
            return f"https://remoteok.com/api?{query}"
        return "https://remoteok.com/api"
    if "remoteok.com" in (parsed.netloc or "").lower():
        return raw
    return DEFAULT_REMOTEOK_API


def remoteok_tag_filters(board_url: str) -> frozenset[str]:
    parsed = urlparse(remoteok_api_url(board_url))
    qs = parse_qs(parsed.query)
    tags: set[str] = set()
    for key in ("tag", "tags"):
        for raw in qs.get(key) or []:
            for part in str(raw).split(","):
                tag = part.strip().lower()
                if tag:
                    tags.add(tag)
    return frozenset(tags)


def _plain_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tags_match(job_tags: list, wanted: frozenset[str]) -> bool:
    if not wanted:
        return True
    have = {str(tag).strip().lower() for tag in job_tags if tag}
    if have & wanted:
        return True
    if wanted <= _DEV_TAG_HINTS and have & _DEV_TAG_HINTS:
        return True
    return False


def parse_remoteok_api_payload(payload: object, *, board_url: str = "") -> list[dict]:
    if not isinstance(payload, list):
        return []
    wanted = remoteok_tag_filters(board_url)
    jobs: list[dict] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        if "legal" in row or "last_updated" in row and "position" not in row:
            continue
        title = (row.get("position") or row.get("title") or "").strip()
        url = (row.get("url") or row.get("apply_url") or "").strip()
        employer = (row.get("company") or "").strip()
        if not title or not url or not employer:
            continue
        tags = row.get("tags") if isinstance(row.get("tags"), list) else []
        if not _tags_match(tags, wanted):
            continue
        location = (row.get("location") or "").strip().rstrip(",")
        description = _plain_text(row.get("description") or "")
        jobs.append(
            listing_job(
                title,
                url,
                location=location or None,
                employer=employer,
                description_text=description or None,
            )
        )
    return jobs


async def fetch_remoteok_board(client, board_url: str, company: dict) -> list[dict]:
    url = remoteok_api_url(board_url or (company.get("ats_url") or company.get("careers_url") or ""))
    response = await client.get(url, headers=HEADERS, timeout=30.0)
    response.raise_for_status()
    return parse_remoteok_api_payload(response.json(), board_url=url)
