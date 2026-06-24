from __future__ import annotations

import re

import requests

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.descriptions import html_to_text


def fetch_greenhouse_job_text(url: str) -> str:
    match = re.search(r"greenhouse\.io/(?:[^/]+/)?jobs/(\d+)", url, re.I)
    if not match:
        return ""
    job_id = match.group(1)
    board_match = re.search(r"greenhouse\.io/([^/]+)/jobs/", url, re.I)
    slug = board_match.group(1) if board_match else ""
    for board in [slug, ""]:
        if not board:
            continue
        api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        try:
            response = requests.get(api, headers=HEADERS, timeout=10)
            if response.ok and response.json().get("content"):
                return html_to_text(response.json()["content"])
        except Exception:
            pass
    return ""


def fetch_lever_job_text(url: str) -> str:
    match = re.search(r"lever\.co/[^/]+/([0-9a-f-]{36})", url, re.I)
    if not match:
        return ""
    api = f"https://api.lever.co/v0/postings/{match.group(1)}"
    try:
        response = requests.get(api, headers=HEADERS, timeout=10)
        if not response.ok:
            return ""
        data = response.json()
        parts = [
            data.get("descriptionPlain") or "",
            data.get("description") or "",
            str(data.get("lists") or ""),
            str(data.get("additional") or ""),
        ]
        return html_to_text("\n".join(parts))
    except Exception:
        return ""


def fetch_recruitee_job_text(url: str) -> str:
    match = re.search(r"([a-z0-9-]+)\.recruitee\.com/o/([a-z0-9-]+)", url, re.I)
    if not match:
        return ""
    company, offer_slug = match.group(1), match.group(2)
    try:
        response = requests.get(
            f"https://{company}.recruitee.com/api/offers/",
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        for offer in response.json().get("offers", []):
            if offer.get("slug") == offer_slug:
                detail = requests.get(
                    f"https://{company}.recruitee.com/api/offers/{offer['id']}",
                    headers=HEADERS,
                    timeout=10,
                )
                if detail.ok:
                    desc = detail.json().get("offer", {}).get("description", "")
                    return html_to_text(desc)
    except Exception:
        pass
    return ""


def fetch_ashby_job_text(url: str) -> str:
    match = re.search(r"ashbyhq\.com/[^/]+/([0-9a-f-]{36})", url, re.I)
    if not match:
        return ""
    org_match = re.search(r"ashbyhq\.com/([^/]+)/", url, re.I)
    org = org_match.group(1) if org_match else ""
    if not org:
        return ""
    api = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensationRanges=true"
    try:
        response = requests.get(api, headers=HEADERS, timeout=10)
        if not response.ok:
            return ""
        for job in response.json().get("jobs", []) or []:
            if job.get("id") == match.group(1) or match.group(1) in (job.get("jobUrl") or ""):
                return html_to_text(job.get("descriptionHtml") or job.get("description") or "")
    except Exception:
        pass
    return ""


_JOB_TEXT_FETCHERS = {
    "greenhouse": fetch_greenhouse_job_text,
    "greenhouse_eu": fetch_greenhouse_job_text,
    "lever": fetch_lever_job_text,
    "lever_eu": fetch_lever_job_text,
    "recruitee": fetch_recruitee_job_text,
    "ashby": fetch_ashby_job_text,
}


def fetch_job_description(url: str, ats_type: str | None = None) -> str:
    fetcher = _JOB_TEXT_FETCHERS.get(ats_type or "")
    if fetcher:
        text = fetcher(url)
        if text:
            return text
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.ok:
            text = html_to_text(response.text)
            if len(text) > 200:
                return text
    except Exception:
        pass
    return ""
