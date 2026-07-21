from __future__ import annotations


def listing_job(
    title: str,
    url: str,
    *,
    location: str | dict | None = None,
    locations: list | None = None,
    employer: str | None = None,
    description_text: str | None = None,
) -> dict:
    job = {"title": (title or "").strip(), "url": (url or "").strip()}
    if location is not None and location != "":
        job["location"] = location
    if locations:
        job["locations"] = locations
    employer_name = (employer or "").strip()
    if employer_name:
        job["employer"] = employer_name
    description = (description_text or "").strip()
    if description:
        job["description_text"] = description
    return job
