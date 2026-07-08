from __future__ import annotations

import httpx

from relocation_jobs.core.ats_detection import HEADERS


def make_fetch_client(concurrency: int = 16) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=concurrency + 4,
            max_keepalive_connections=concurrency,
        ),
    )
