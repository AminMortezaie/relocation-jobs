from __future__ import annotations

from urllib.parse import urlparse

from relocation_jobs.core.ats_detection import (
    HEADERS,
    _parse_workday_board_url,
    _workday_api_and_base,
)
from relocation_jobs.scrape.listing import listing_job


def workday_job_detail_api_url(url: str) -> str | None:
    parsed = urlparse((url or "").split("?")[0])
    host = (parsed.hostname or "").lower()
    if "myworkdayjobs.com" not in host and "myworkdaysite.com" not in host:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if "job" not in parts:
        return None
    job_idx = parts.index("job")
    if job_idx < 1 or job_idx >= len(parts) - 1:
        return None
    job_slug = parts[-1]
    board = _parse_workday_board_url(host, parts[:job_idx])
    if not board:
        return None
    tenant, site, _locale = board
    scheme = parsed.scheme or "https"
    return f"{scheme}://{host}/wday/cxs/{tenant}/{site}/job/{job_slug}"


async def fetch_workday_board(client, board_url: str, company: dict) -> list[dict]:
    api, base = _workday_api_and_base(board_url)
    if not api or not base:
        return []
    jobs: list[dict] = []
    offset = 0
    limit = 20
    total: int | None = None
    while offset <= 2000:
        response = await client.post(
            api,
            json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=25.0,
        )
        response.raise_for_status()
        data = response.json()
        postings = data.get("jobPostings") or []
        if total is None:
            total = int(data.get("total") or len(postings))
        for posting in postings:
            path = (posting.get("externalPath") or "").strip()
            title = (posting.get("title") or "").strip()
            if not path or not title:
                continue
            location = (
                (posting.get("locationsText") or posting.get("location") or "").strip() or None
            )
            jobs.append(listing_job(title, base.rstrip("/") + path, location=location))
        offset += limit
        if not postings or offset >= total:
            break
    return jobs
