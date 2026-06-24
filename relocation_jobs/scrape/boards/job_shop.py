from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS, _parse_job_shop_config
from relocation_jobs.scrape.listing import listing_job

JOB_SHOP_TYPESENSE_URL = "https://api.my-job-shop.com/api/typesense/multi_search"


def job_shop_search_payload(tenant_id: str, vanity: str, *, page: int = 1, per_page: int = 100) -> dict:
    return {
        "searches": [{
            "collection": "offers",
            "q": "*",
            "query_by": "title",
            "per_page": per_page,
            "page": page,
            "filter_by": f"tenant_id:={tenant_id}&&backoffice_vanity:={vanity}&&status:=ACTIVE",
        }],
    }


def jobs_from_job_shop_result(result: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for hit in result.get("hits") or []:
        doc = hit.get("document") or hit
        title = (doc.get("title") or "").strip()
        url = (doc.get("url") or "").strip()
        if not title or not url:
            continue
        key = (title.casefold(), url)
        if key in seen:
            continue
        seen.add(key)
        jobs.append(listing_job(title, url))
    return jobs


async def fetch_job_shop_board(client, board_url: str, company: dict) -> list[dict]:
    careers_url = (company.get("careers_url") or board_url).strip()
    page_url = careers_url.split("#", 1)[0].strip() or careers_url
    if "/search" not in page_url:
        page_url = page_url.rstrip("/") + "/search"
    page_response = await client.get(page_url, headers=HEADERS, timeout=20.0)
    page_response.raise_for_status()
    config = _parse_job_shop_config(page_response.text, careers_url)
    if not config:
        return []
    api_key, tenant_id, vanity = config
    headers = {
        **HEADERS,
        "X-TYPESENSE-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    jobs: list[dict] = []
    page = 1
    per_page = 100
    total = None
    while True:
        response = await client.post(
            JOB_SHOP_TYPESENSE_URL,
            json=job_shop_search_payload(tenant_id, vanity, page=page, per_page=per_page),
            headers=headers,
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        result = (data.get("results") or [{}])[0]
        if total is None:
            total = int(result.get("found") or 0)
        jobs.extend(jobs_from_job_shop_result(result))
        if page * per_page >= total or not result.get("hits"):
            break
        page += 1
    return jobs
