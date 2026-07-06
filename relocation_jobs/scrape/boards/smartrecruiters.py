from __future__ import annotations

import re

from relocation_jobs.core.ats_detection import (
    HEADERS,
    _smartrecruiters_api_url,
    _smartrecruiters_company_id,
)
from relocation_jobs.scrape.listing import listing_job

_SMARTRECRUITERS_POSTING_URL_RE = re.compile(
    r"smartrecruiters\.com/(?:v1/companies/)?([A-Za-z0-9_-]+)(?:/postings)?/(\d+)",
    re.I,
)
_JOB_AD_SECTION_ORDER = (
    "companyDescription",
    "jobDescription",
    "qualifications",
    "additionalInformation",
)


def smartrecruiters_location_text(raw: dict | None) -> str:
    if not isinstance(raw, dict):
        return ""
    full = (raw.get("fullLocation") or raw.get("full_location") or "").strip()
    if full:
        return full
    parts = [(raw.get("city") or "").strip(), (raw.get("country") or "").strip()]
    return ", ".join(dict.fromkeys(part for part in parts if part))


def smartrecruiters_postings_page_url(company_id: str, offset: int) -> str:
    return (
        f"{_smartrecruiters_api_url(company_id)}"
        f"?limit=100&offset={offset}&include=locations"
    )


def smartrecruiters_job_url(company_id: str, job_id: str) -> str:
    return f"https://jobs.smartrecruiters.com/{company_id}/{job_id}"


def smartrecruiters_posting_ids_from_url(url: str) -> tuple[str, str] | None:
    match = _SMARTRECRUITERS_POSTING_URL_RE.search(url or "")
    if not match:
        return None
    return match.group(1), match.group(2)


def smartrecruiters_posting_detail_url(url: str) -> str | None:
    ids = smartrecruiters_posting_ids_from_url(url)
    if not ids:
        return None
    company_id, posting_id = ids
    return f"{_smartrecruiters_api_url(company_id)}/{posting_id}"


def smartrecruiters_job_ad_html(posting: dict) -> str:
    sections = (posting.get("jobAd") or {}).get("sections") or {}
    parts: list[str] = []
    for key in _JOB_AD_SECTION_ORDER:
        section = sections.get(key) or {}
        title = (section.get("title") or "").strip()
        text = (section.get("text") or "").strip()
        if not text:
            continue
        if title:
            parts.append(f"<h3>{title}</h3>")
        parts.append(text)
    return "\n".join(parts)


async def fetch_smartrecruiters_board(client, board_url: str, company: dict) -> list[dict]:
    company_id = _smartrecruiters_company_id(board_url)
    if not company_id:
        return []
    jobs: list[dict] = []
    offset = 0
    while True:
        response = await client.get(
            smartrecruiters_postings_page_url(company_id, offset),
            headers=HEADERS,
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content") or []
        for row in content:
            title = (row.get("name") or "").strip()
            job_id = (row.get("id") or "").strip()
            if not title or not job_id:
                continue
            jobs.append(
                listing_job(
                    title,
                    smartrecruiters_job_url(company_id, job_id),
                    location=smartrecruiters_location_text(row.get("location")),
                )
            )
        offset += len(content)
        total = int(payload.get("totalFound") or offset)
        if not content or offset >= total:
            break
    return jobs
