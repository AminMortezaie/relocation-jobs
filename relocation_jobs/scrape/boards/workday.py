from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS, _workday_api_and_base
from relocation_jobs.scrape.listing import listing_job


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
