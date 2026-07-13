from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.listing import listing_job


async def fetch_successfactors_board(client, board_url: str, company: dict) -> list[dict]:
    careers_url = (company.get("careers_url") or board_url).strip()
    if not careers_url:
        return []

    # SAP SuccessFactors renders jobs via an AJAX API embedded in data-url
    # on the .js-results element. Fall back to scraping the page to find it.
    response = await client.get(careers_url, headers=HEADERS, timeout=15.0)
    response.raise_for_status()
    html = response.text

    import re
    m = re.search(r'data-url\s*=\s*"(/en-[a-z]{2}/api/job/getjobs[^"]*)"', html)
    if not m:
        return []
    api_path = m.group(1)
    domain = careers_url.split("/en-")[0]
    api_url = domain + api_path

    resp = await client.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items") or []
    base_url = careers_url.rstrip("/")

    jobs = []
    for item in items:
        title = (item.get("headline") or "").strip()
        href = (item.get("href") or "").strip()
        location = (item.get("location") or "").strip()
        if not title:
            continue
        job_url = href if href.startswith("http") else f"{base_url}/{href.lstrip('/')}"
        jobs.append(listing_job(title, job_url, location=location or None))

    return jobs
