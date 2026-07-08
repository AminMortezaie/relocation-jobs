from __future__ import annotations

import re
from typing import NamedTuple

import requests

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.boards.ashby import ashby_job_detail, ashby_job_ids_from_url
from relocation_jobs.scrape.boards.greenhouse import (
    greenhouse_job_detail,
    greenhouse_job_ids_from_url,
)
from relocation_jobs.scrape.boards.hibob import fetch_hibob_job_detail as hibob_job_detail_fetch
from relocation_jobs.scrape.boards.smartrecruiters import (
    smartrecruiters_job_ad_html,
    smartrecruiters_location_text,
    smartrecruiters_posting_detail_url,
)
from relocation_jobs.scrape.boards.workday import workday_job_detail_api_url
from relocation_jobs.scrape.descriptions import html_to_readable


class JobFetchResult(NamedTuple):
    text: str
    location: str


def _empty_fetch() -> JobFetchResult:
    return JobFetchResult("", "")


def _recruitee_location_label(offer: dict) -> str:
    location = (offer.get("location") or "").strip()
    if location:
        return location
    city = (offer.get("city") or "").strip()
    country = (offer.get("country") or offer.get("country_code") or "").strip()
    parts = [part for part in (city, country) if part]
    return ", ".join(dict.fromkeys(parts))


def fetch_greenhouse_job_detail(url: str) -> JobFetchResult:
    ids = greenhouse_job_ids_from_url(url)
    if ids:
        content, location = greenhouse_job_detail(ids[0], ids[1])
        if content:
            return JobFetchResult(content, location)
    match = re.search(r"greenhouse\.io/(?:[^/]+/)?jobs/(\d+)", url, re.I)
    if not match:
        return _empty_fetch()
    job_id = match.group(1)
    board_match = re.search(r"greenhouse\.io/([^/]+)/jobs/", url, re.I)
    slug = board_match.group(1) if board_match else ""
    if not slug or slug in ("embed", "jobs"):
        return _empty_fetch()
    content, location = greenhouse_job_detail(slug, job_id)
    return JobFetchResult(content, location)


def fetch_greenhouse_job_text(url: str) -> str:
    return fetch_greenhouse_job_detail(url).text


def fetch_lever_job_detail(url: str) -> JobFetchResult:
    match = re.search(r"lever\.co/[^/]+/([0-9a-f-]{36})", url, re.I)
    if not match:
        return _empty_fetch()
    api = f"https://api.lever.co/v0/postings/{match.group(1)}"
    try:
        response = requests.get(api, headers=HEADERS, timeout=10)
        if not response.ok:
            return _empty_fetch()
        data = response.json()
        location = ((data.get("categories") or {}).get("location") or "").strip()
        parts = [
            data.get("descriptionPlain") or "",
            data.get("description") or "",
            str(data.get("lists") or ""),
            str(data.get("additional") or ""),
        ]
        plain = (data.get("descriptionPlain") or "").strip()
        if plain:
            return JobFetchResult(plain, location)
        readable = html_to_readable("\n".join(parts))
        return JobFetchResult(readable, location)
    except Exception:
        return _empty_fetch()


def fetch_lever_job_text(url: str) -> str:
    return fetch_lever_job_detail(url).text


def fetch_recruitee_job_detail(url: str) -> JobFetchResult:
    match = re.search(r"([a-z0-9-]+)\.recruitee\.com/o/([a-z0-9-]+)", url, re.I)
    if not match:
        return _empty_fetch()
    company, offer_slug = match.group(1), match.group(2)
    try:
        response = requests.get(
            f"https://{company}.recruitee.com/api/offers/",
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        for offer in response.json().get("offers", []):
            if offer.get("slug") != offer_slug:
                continue
            detail = requests.get(
                f"https://{company}.recruitee.com/api/offers/{offer['id']}",
                headers=HEADERS,
                timeout=10,
            )
            if not detail.ok:
                continue
            offer = detail.json().get("offer", {}) or {}
            parts = [
                (offer.get("description") or "").strip(),
                (offer.get("requirements") or "").strip(),
            ]
            html = "\n\n".join(part for part in parts if part)
            return JobFetchResult(
                html_to_readable(html),
                _recruitee_location_label(offer),
            )
    except Exception:
        pass
    return _empty_fetch()


def fetch_recruitee_job_text(url: str) -> str:
    return fetch_recruitee_job_detail(url).text


def fetch_smartrecruiters_job_detail(url: str) -> JobFetchResult:
    detail_url = smartrecruiters_posting_detail_url(url)
    if not detail_url:
        return _empty_fetch()
    try:
        response = requests.get(detail_url, headers=HEADERS, timeout=10)
        if not response.ok:
            return _empty_fetch()
        payload = response.json()
        html = smartrecruiters_job_ad_html(payload)
        if not html.strip():
            return _empty_fetch()
        return JobFetchResult(
            html,
            smartrecruiters_location_text(payload.get("location")),
        )
    except Exception:
        pass
    return _empty_fetch()


def fetch_smartrecruiters_job_text(url: str) -> str:
    return fetch_smartrecruiters_job_detail(url).text


def fetch_ashby_job_detail(url: str) -> JobFetchResult:
    ids = ashby_job_ids_from_url(url)
    if not ids:
        return _empty_fetch()
    content, location = ashby_job_detail(ids[0], ids[1])
    return JobFetchResult(content, location)


def fetch_ashby_job_text(url: str) -> str:
    return fetch_ashby_job_detail(url).text


def fetch_hibob_job_detail(url: str) -> JobFetchResult:
    text, location = hibob_job_detail_fetch(url)
    return JobFetchResult(text, location)


def fetch_hibob_job_text(url: str) -> str:
    return fetch_hibob_job_detail(url).text


def fetch_workday_job_detail(url: str) -> JobFetchResult:
    api = workday_job_detail_api_url(url)
    if not api:
        return _empty_fetch()
    try:
        response = requests.get(
            api,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        if not response.ok:
            return _empty_fetch()
        info = response.json().get("jobPostingInfo") or {}
        html = (info.get("jobDescription") or "").strip()
        if not html:
            return _empty_fetch()
        location = (info.get("location") or "").strip()
        return JobFetchResult(html_to_readable(html), location)
    except Exception:
        return _empty_fetch()


def fetch_workday_job_text(url: str) -> str:
    return fetch_workday_job_detail(url).text


_JOB_DETAIL_FETCHERS = {
    "greenhouse": fetch_greenhouse_job_detail,
    "greenhouse_eu": fetch_greenhouse_job_detail,
    "lever": fetch_lever_job_detail,
    "lever_eu": fetch_lever_job_detail,
    "recruitee": fetch_recruitee_job_detail,
    "ashby": fetch_ashby_job_detail,
    "hibob": fetch_hibob_job_detail,
    "smartrecruiters": fetch_smartrecruiters_job_detail,
    "workday": fetch_workday_job_detail,
}


_JD_SIGNAL_PATTERNS = re.compile(
    r"(?i)(?:"
    r"responsibilit|requirement|qualification|what you.ll |about the role|"
    r"the ideal candidate|about you\b|key skills|job description|"
    r"we are looking for|your profile|what we expect|"
    r"day to day|main tasks|key accountabilities|"
    r"education and experience|minimum requirement|preferred qualification"
    r")"
)


def _looks_like_job_description(text: str) -> bool:
    if not text:
        return False
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    long_lines = sum(1 for l in lines if len(l) > 60)
    if _JD_SIGNAL_PATTERNS.search(text):
        return long_lines >= 2
    bullet_count = text.count("• ")
    return long_lines >= 5 and bullet_count >= 2


def fetch_job_detail(url: str, ats_type: str | None = None) -> JobFetchResult:
    fetcher = _JOB_DETAIL_FETCHERS.get(ats_type or "")
    if fetcher:
        result = fetcher(url)
        if result.text:
            return result
    if (ats_type or "") not in ("greenhouse", "greenhouse_eu"):
        result = fetch_greenhouse_job_detail(url)
        if result.text:
            return result
    if (ats_type or "") != "ashby":
        result = fetch_ashby_job_detail(url)
        if result.text:
            return result
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.ok:
            text = html_to_readable(response.text)
            if len(text) > 300 and _looks_like_job_description(text):
                return JobFetchResult(text, "")
    except Exception:
        pass
    return _empty_fetch()


def fetch_job_description(url: str, ats_type: str | None = None) -> str:
    return fetch_job_detail(url, ats_type).text
