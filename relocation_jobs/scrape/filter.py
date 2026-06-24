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
        if job.get("location") is not None:
            entry["location"] = job["location"]
        if job.get("locations") is not None:
            entry["locations"] = job["locations"]
        out.append(entry)
    return out
