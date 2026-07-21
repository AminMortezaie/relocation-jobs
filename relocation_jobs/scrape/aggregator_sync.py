from __future__ import annotations

from collections import defaultdict
from datetime import date

from relocation_jobs.catalog.repo import sync_aggregator_employer_jobs
from relocation_jobs.fetch.log import log_event
from relocation_jobs.scrape.filter import filter_relevant_jobs

AGGREGATOR_ATS_TYPES = frozenset({"remoteok", "remotedxb"})
SOURCED_ATS_TYPE = "sourced"

_SOURCE_LABEL = {
    "remoteok": "remoteok",
    "remotedxb": "remotedxb",
}


def is_aggregator_ats(ats_type: str | None) -> bool:
    return (ats_type or "").strip().lower() in AGGREGATOR_ATS_TYPES


def should_skip_country_fetch(ats_type: str | None) -> bool:
    return (ats_type or "").strip().lower() == SOURCED_ATS_TYPE


def group_jobs_by_employer(jobs: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for job in jobs:
        employer = (job.get("employer") or "").strip()
        if not employer:
            continue
        entry = {
            "title": (job.get("title") or "").strip(),
            "url": (job.get("url") or "").strip(),
        }
        location = (job.get("location") or "").strip()
        if location:
            entry["location"] = location
        if job.get("locations") is not None:
            entry["locations"] = job["locations"]
        description = (job.get("description_text") or "").strip()
        if description:
            entry["description_text"] = description
        if entry["title"] and entry["url"]:
            grouped[employer].append(entry)
    return dict(grouped)


def sync_aggregator_board(
    country_key: str,
    source_company: dict,
    raw_jobs: list[dict],
    *,
    relevant_only: bool = True,
) -> tuple[int, int]:
    ats = (source_company.get("ats_type") or "").strip().lower()
    source = _SOURCE_LABEL.get(ats, ats or "aggregator")
    matched = filter_relevant_jobs(raw_jobs, relevant_only)
    grouped = group_jobs_by_employer(matched)
    employers = 0
    job_total = 0
    careers_fallback = (
        (source_company.get("careers_url") or source_company.get("ats_url") or "").strip()
    )
    for employer, jobs in grouped.items():
        if not jobs:
            continue
        sync_aggregator_employer_jobs(
            country_key,
            employer,
            jobs,
            source=source,
            careers_url=careers_fallback or jobs[0]["url"],
        )
        employers += 1
        job_total += len(jobs)
    log_event(
        f"aggregator sync employers={employers} jobs={job_total}",
        company=source_company.get("name") or "",
    )
    return employers, job_total


def aggregator_success_line(prefix: str, employers: int, jobs: int) -> str:
    return f"{prefix} — aggregator: {jobs} job(s) across {employers} employer(s)"


def today_iso() -> str:
    return date.today().isoformat()
