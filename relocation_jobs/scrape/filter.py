from __future__ import annotations

from relocation_jobs.scrape.relevance import is_relevant


def filter_relevant_jobs(jobs: list[dict], relevant_only: bool) -> list[dict]:
    out: list[dict] = []
    for job in jobs:
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()
        if not title or not url:
            continue
        if relevant_only and not is_relevant(title):
            continue
        entry = {"title": title, "url": url}
        location = (job.get("location") or "").strip()
        if location:
            entry["location"] = location
        if job.get("locations") is not None:
            entry["locations"] = job["locations"]
        employer = (job.get("employer") or "").strip()
        if employer:
            entry["employer"] = employer
        description = (job.get("description_text") or "").strip()
        if description:
            entry["description_text"] = description
        out.append(entry)
    return out
