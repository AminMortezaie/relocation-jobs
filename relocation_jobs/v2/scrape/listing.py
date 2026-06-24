from __future__ import annotations


def listing_job(
    title: str,
    url: str,
    *,
    location: str | dict | None = None,
    locations: list | None = None,
) -> dict:
    job = {"title": (title or "").strip(), "url": (url or "").strip()}
    if location is not None and location != "":
        job["location"] = location
    if locations:
        job["locations"] = locations
    return job
