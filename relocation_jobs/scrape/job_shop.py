"""Job Shop / Talents Connect Typesense board scraper."""

from __future__ import annotations

from relocation_jobs.core.ats_detection import HEADERS, _parse_job_shop_config
from relocation_jobs.scrape.http import httpx, requests
from relocation_jobs.scrape.relevance import is_relevant

JOB_SHOP_TYPESENSE_URL = "https://api.my-job-shop.com/api/typesense/multi_search"


def job_shop_search_payload(
    tenant_id: str,
    vanity: str,
    *,
    page: int = 1,
    per_page: int = 100,
) -> dict:
    return {
        "searches": [{
            "collection": "offers",
            "q": "*",
            "query_by": "title",
            "per_page": per_page,
            "page": page,
            "filter_by": (
                f"tenant_id:={tenant_id}&&backoffice_vanity:={vanity}&&status:=ACTIVE"
            ),
        }],
    }


def jobs_from_job_shop_response(data: dict, *, relevant_only: bool = True) -> list[dict]:
    jobs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for result in data.get("results", []):
        for hit in result.get("hits", []):
            doc = hit.get("document") or hit
            title = (doc.get("title") or "").strip()
            url = (doc.get("url") or "").strip()
            if not title or not url:
                continue
            if relevant_only and not is_relevant(title):
                continue
            key = (title.casefold(), url)
            if key in seen:
                continue
            seen.add(key)
            jobs.append({"title": title, "url": url})
    return jobs


def scrape_job_shop(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    """Talents Connect / Job Shop boards (api.my-job-shop.com + Typesense)."""
    page_url = (careers_url or "").split("#", 1)[0].strip() or careers_url
    if not page_url:
        return []
    if "/search" not in page_url:
        page_url = page_url.rstrip("/") + "/search"

    try:
        r = requests.get(page_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return []

    config = _parse_job_shop_config(r.text, careers_url)
    if not config:
        print(f"    Job Shop error ({careers_url}): could not parse board config")
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
    try:
        while True:
            r = requests.post(
                JOB_SHOP_TYPESENSE_URL,
                json=job_shop_search_payload(
                    tenant_id, vanity, page=page, per_page=per_page
                ),
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            result = (data.get("results") or [{}])[0]
            if total is None:
                total = int(result.get("found") or 0)
            batch = jobs_from_job_shop_response(
                {"results": [result]},
                relevant_only=relevant_only,
            )
            jobs.extend(batch)
            if page * per_page >= total or not result.get("hits"):
                break
            page += 1
        return jobs
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return jobs


async def scrape_job_shop_async(
    client: httpx.AsyncClient,
    careers_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    page_url = (careers_url or "").split("#", 1)[0].strip() or careers_url
    if not page_url:
        return []
    if "/search" not in page_url:
        page_url = page_url.rstrip("/") + "/search"

    try:
        r = await client.get(page_url, timeout=20.0)
        r.raise_for_status()
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return []

    config = _parse_job_shop_config(r.text, careers_url)
    if not config:
        print(f"    Job Shop error ({careers_url}): could not parse board config")
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
    try:
        while True:
            r = await client.post(
                JOB_SHOP_TYPESENSE_URL,
                json=job_shop_search_payload(
                    tenant_id, vanity, page=page, per_page=per_page
                ),
                headers=headers,
                timeout=20.0,
            )
            r.raise_for_status()
            data = r.json()
            result = (data.get("results") or [{}])[0]
            if total is None:
                total = int(result.get("found") or 0)
            batch = jobs_from_job_shop_response(
                {"results": [result]},
                relevant_only=relevant_only,
            )
            jobs.extend(batch)
            if page * per_page >= total or not result.get("hits"):
                break
            page += 1
        return jobs
    except Exception as e:
        print(f"    Job Shop error ({careers_url}): {e}")
        return jobs
