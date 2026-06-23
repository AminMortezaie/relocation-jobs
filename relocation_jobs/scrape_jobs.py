#!/usr/bin/env python3
"""
Scrape careers pages and find matching backend jobs.

Compatibility shim — implementation lives in ``relocation_jobs.scrape``.
"""

from __future__ import annotations

import asyncio
import sys

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE
from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.scrape import _compat
from relocation_jobs.scrape import ipc as _scrape_ipc

for _name in dir(_compat):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_compat, _name)
del _name

from relocation_jobs.core import ats_detection as _ats_detection
PLAYWRIGHT_AVAILABLE = _ats_detection.PLAYWRIGHT_AVAILABLE

from relocation_jobs.scrape.dispatch import (
    apply_known_ats_override as _apply_known_ats_override,
    effective_cached_ats as _effective_cached_ats,
    get_jobs,
    get_jobs_async,
    persist_detected_ats as _persist_detected_ats,
)
from relocation_jobs.scrape.enrich import (
    enrich_jobs,
    enrich_jobs_async_with_client,
    enrich_one_job as _enrich_one_job,
    enrich_one_job_async as _enrich_one_job_async,
    fetch_job_description,
    fetch_job_description_async,
)
from relocation_jobs.scrape.ipc import (
    clear_progress_reporter,
    clear_review_reporter,
    emit_panel_ipc as _emit_panel_ipc,
    report_progress as _report_progress,
    report_review_jobs as _report_review_jobs,
    review_entry as _review_entry,
    review_filtered_jobs as _review_filtered_jobs,
    set_progress_reporter,
    set_review_reporter,
)
from relocation_jobs.scrape.runner import (
    process_company_async as _process_company_async,
    run_file_async,
)

if HTTPX_AVAILABLE:
    import httpx  # noqa: F401


async def _jobs_from_listing_html_async(
    html: str,
    page_url: str,
    client: httpx.AsyncClient,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    from relocation_jobs.scrape import listing as _scrape_listing

    return await _scrape_listing.jobs_from_listing_html_async(
        html,
        page_url,
        client,
        relevant_only=relevant_only,
        detail_fetcher=_fetch_job_detail_title,
    )


async def scrape_ashby_async(
    client: httpx.AsyncClient,
    ats_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    from relocation_jobs.scrape import ashby as _scrape_ashby

    return await _scrape_ashby.scrape_ashby_async(
        client,
        ats_url,
        relevant_only=relevant_only,
        playwright_fallback=scrape_with_playwright,
    )


def scrape_personio(ats_url: str, *, relevant_only: bool = True) -> list[dict]:
    from relocation_jobs.scrape import personio as _scrape_personio

    return _scrape_personio.scrape_personio(
        ats_url,
        relevant_only=relevant_only,
        html_scraper=scrape_personio_html,
    )


def scrape_jibe(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    from relocation_jobs.scrape import misc as _scrape_misc

    return _scrape_misc.scrape_jibe(
        careers_url,
        relevant_only=relevant_only,
        playwright_available=PLAYWRIGHT_AVAILABLE,
        playwright_cm=sync_playwright,
    )


def scrape_atlassian(careers_url: str, *, relevant_only: bool = True) -> list[dict]:
    from relocation_jobs.scrape import misc as _scrape_misc

    return _scrape_misc.scrape_atlassian(
        careers_url,
        relevant_only=relevant_only,
        playwright_available=PLAYWRIGHT_AVAILABLE,
        playwright_cm=sync_playwright,
    )


def _report_activity(message: str, *, detail: str = "") -> None:
    _scrape_ipc.report_activity(message, detail=detail)


def scrape_teamtailor(
    api_key_or_url: str,
    careers_url: str,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    from relocation_jobs.scrape import teamtailor as _scrape_teamtailor

    return _scrape_teamtailor.scrape_teamtailor(
        api_key_or_url,
        careers_url,
        relevant_only=relevant_only,
        playwright_fallback=scrape_with_playwright,
        activity_reporter=_report_activity,
        listing_link_collector=_collect_listing_job_links,
        candidates_to_jobs=_listing_candidates_to_jobs,
    )


def run_country(
    country_key: str,
    *,
    target: str | None = None,
    skip_filled: bool = False,
    enrich_only: bool = False,
    skip_enriched: bool = False,
    workers: int = DEFAULT_WORKERS,
    ats_type: str | None = None,
) -> None:
    asyncio.run(
        run_file_async(
            country_key,
            target=target,
            skip_filled=skip_filled,
            enrich_only=enrich_only,
            skip_enriched=skip_enriched,
            concurrency=workers,
            ats_type=ats_type,
        )
    )


def main() -> None:
    country_keys = ["germany"]
    target = None
    skip_filled = False
    enrich_only = False
    skip_enriched = False
    run_all = False
    workers = DEFAULT_WORKERS
    ats_type = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--skip-filled":
            skip_filled = True
        elif arg == "--enrich-only":
            enrich_only = True
        elif arg == "--skip-enriched":
            skip_enriched = True
        elif arg == "--all":
            run_all = True
        elif arg == "--serial":
            workers = 1
        elif arg == "--workers":
            i += 1
            if i >= len(args):
                print("--workers requires a number")
                return
            workers = max(1, int(args[i]))
        elif arg.startswith("--workers="):
            workers = max(1, int(arg.split("=", 1)[1]))
        elif arg == "--country":
            i += 1
            if i >= len(args):
                print("--country requires a country key (e.g. uk, germany)")
                return
            country_keys = [args[i]]
        elif arg.startswith("--country="):
            country_keys = [arg.split("=", 1)[1]]
        elif arg == "--ats":
            i += 1
            if i >= len(args):
                print("--ats requires an ATS type (e.g. greenhouse, lever)")
                return
            ats_type = args[i]
        elif arg.startswith("--ats="):
            ats_type = arg.split("=", 1)[1]
        else:
            target = arg
        i += 1

    if run_all:
        country_keys = sorted(SUPPORTED_COUNTRIES)

    for country_key in country_keys:
        run_country(
            country_key,
            target=target,
            skip_filled=skip_filled,
            enrich_only=enrich_only,
            skip_enriched=skip_enriched,
            workers=workers,
            ats_type=ats_type,
        )

    if len(country_keys) > 1:
        print(f"\nAll done — processed {len(country_keys)} countries.")


if __name__ == "__main__":
    main()
