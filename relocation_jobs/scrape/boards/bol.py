from __future__ import annotations

from urllib.parse import urlparse

from relocation_jobs.core.ats_constants import BOL_CAREERS_API
from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.listing import listing_job

_BOL_PAGE_SIZE = 10


def bol_jobs_path_prefix(careers_url: str) -> str:
    path = (urlparse(careers_url).path or "").lower()
    if path.startswith("/nl/"):
        return "https://careers.bol.com/nl/vacatures"
    return "https://careers.bol.com/en/jobs"


def bol_search_payload(careers_url: str, *, page: int = 1) -> dict:
    return {
        "page": page,
        "jobFamily": [],
        "expertise": [],
        "yearsOfExperience": [],
        "educationLevel": [],
        "language": [],
    }


def _bol_office_label(office: object) -> str | None:
    if isinstance(office, dict):
        label = (office.get("label") or office.get("name") or "").strip()
        return label or None
    if isinstance(office, str):
        text = office.strip()
        return text or None
    return None


def parse_bol_response(data: dict, *, path_prefix: str) -> list[dict]:
    hits = data.get("hits", {}).get("hits")
    if hits is None:
        hits = (data.get("results") or {}).get("hits", {}).get("hits", [])
    jobs: list[dict] = []
    base = path_prefix.rstrip("/")
    for hit in hits or []:
        src = hit.get("_source") or {}
        title = (src.get("title") or src.get("publicatienaam") or src.get("post_title") or "").strip()
        if not title:
            continue
        job_id = src.get("id")
        slug = (src.get("slug") or "").strip()
        if job_id:
            job_url = f"{base}/_/{job_id}/"
        elif slug.startswith("/"):
            job_url = f"https://careers.bol.com{slug}"
        elif slug:
            job_url = slug
        else:
            job_url = f"{base}/"
        jobs.append(
            listing_job(title, job_url, location=_bol_office_label(src.get("office"))),
        )
    return jobs


def bol_total_jobs(data: dict) -> int:
    total = (data.get("hits") or {}).get("total")
    if isinstance(total, dict):
        return int(total.get("value") or 0)
    if isinstance(total, int):
        return total
    legacy = (data.get("results") or {}).get("hits", {}).get("total")
    if isinstance(legacy, dict):
        return int(legacy.get("value") or 0)
    return 0


async def fetch_bol_board(client, board_url: str, company: dict) -> list[dict]:
    careers_url = (company.get("careers_url") or board_url).strip()
    path_prefix = bol_jobs_path_prefix(careers_url)
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": careers_url or "https://careers.bol.com/en/jobs/",
    }
    jobs: list[dict] = []
    page = 1
    total = 0
    while page <= 100:
        response = await client.post(
            BOL_CAREERS_API,
            json=bol_search_payload(careers_url, page=page),
            headers=headers,
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("success") is False:
            break
        batch = parse_bol_response(data, path_prefix=path_prefix)
        if not batch:
            break
        jobs.extend(batch)
        if not total:
            total = bol_total_jobs(data)
        if total and len(jobs) >= total:
            break
        if len(batch) < _BOL_PAGE_SIZE:
            break
        page += 1
    return jobs
