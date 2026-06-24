from __future__ import annotations

import logging
from typing import Any

import httpx
import requests
from requests import Response

from relocation_jobs.fetch.log import get_fetch_log_context, log_http_exchange

FETCH_HTTP_KIND = "fetch_http_kind"
FETCH_JOB_URL = "fetch_job_url"
FETCH_JOB_TITLE = "fetch_job_title"


def create_scrape_http_client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        event_hooks={"response": [_httpx_log_response]},
        **kwargs,
    )


def http_extensions(
    *,
    kind: str,
    job_url: str | None = None,
    job_title: str | None = None,
) -> dict:
    ext: dict = {FETCH_HTTP_KIND: kind}
    if job_url:
        ext[FETCH_JOB_URL] = job_url
    if job_title:
        ext[FETCH_JOB_TITLE] = job_title
    return ext


def _kind_from_request(request: httpx.Request) -> str:
    ext = request.extensions or {}
    kind = ext.get(FETCH_HTTP_KIND)
    if kind:
        return str(kind)
    return _guess_http_kind(str(request.url))


def _guess_http_kind(url: str) -> str:
    low = url.lower()
    if "boards-api" in low and "/jobs/" in low:
        return "job"
    if any(token in low for token in ("boards-api", "/api/offers", "api.lever.co", "posting-api")):
        return "board"
    return "http"


def _request_body_text(request: httpx.Request) -> str | None:
    content = request.content
    if not content:
        return None
    try:
        return content.decode("utf-8", errors="replace")
    except Exception:
        return f"<bytes len={len(content)}>"


async def _httpx_log_response(response: httpx.Response) -> None:
    await response.aread()
    request = response.request
    kind = _kind_from_request(request)
    ext = request.extensions or {}
    level = logging.INFO if kind in ("job", "board") else logging.DEBUG
    try:
        body = response.text
    except Exception:
        body = ""
    log_http_exchange(
        kind=kind,
        method=request.method,
        url=str(request.url),
        job_url=ext.get(FETCH_JOB_URL),
        job_title=ext.get(FETCH_JOB_TITLE),
        request_body=_request_body_text(request),
        response_status=response.status_code,
        response_body=body,
        response_bytes=len(response.content or b""),
        level=level,
        **get_fetch_log_context(),
    )


def logged_requests_get(
    url: str,
    *,
    kind: str = "job",
    job_url: str | None = None,
    job_title: str | None = None,
    **kwargs: Any,
) -> Response:
    ctx = get_fetch_log_context()
    try:
        response = requests.get(url, **kwargs)
    except Exception as exc:
        log_http_exchange(
            kind=kind,
            method="GET",
            url=url,
            job_url=job_url or url,
            job_title=job_title,
            error=str(exc),
            level=logging.ERROR,
            **ctx,
        )
        raise
    log_http_exchange(
        kind=kind,
        method="GET",
        url=url,
        job_url=job_url or url,
        job_title=job_title,
        response_status=response.status_code,
        response_body=response.text,
        response_bytes=len(response.content or b""),
        level=logging.INFO,
        **ctx,
    )
    return response
