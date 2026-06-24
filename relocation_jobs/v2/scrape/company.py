from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import date

from relocation_jobs.core.location_tags import filter_jobs_by_expected_locations
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.v2.scrape.filter import filter_relevant_jobs
from relocation_jobs.v2.scrape.merge import merge_matching_jobs, now_iso

FetchBoard = Callable[..., Awaitable[list[dict]]]
EnrichBoard = Callable[..., Awaitable[list[dict]]]
_ERROR_RE = re.compile(r" — Error: (.+)$")


def _today() -> str:
    return date.today().isoformat()


def _company_line(company: dict, index: int, total: int) -> str:
    name = company.get("name") or ""
    city = company.get("city", "?")
    return f"[{index}/{total}] {name} ({city})"


def _persist(company: dict, save_fn) -> None:
    if save_fn:
        save_fn()


async def process_company(
    client,
    company: dict,
    index: int,
    total: int,
    *,
    fetch_board: FetchBoard,
    enrich_board: EnrichBoard | None = None,
    save_fn=None,
    enrich_only: bool = False,
    skip_enriched: bool = False,
    enrich_concurrency: int = 4,
    catalog_country: str = "",
) -> tuple[str, int]:
    prefix = _company_line(company, index, total)
    company["updated"] = now_iso()

    if enrich_only:
        jobs = company.get("matching_jobs") or []
        if not jobs:
            return f"{prefix} — no jobs to enrich", 0
        if enrich_board is None:
            return f"{prefix} — enrich not configured", 0
        jobs = await enrich_board(
            client, jobs, company,
            only_missing=skip_enriched,
            concurrency=enrich_concurrency,
        )
        company["matching_jobs"] = jobs
        company["updated"] = now_iso()
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        _persist(company, save_fn)
        return f"{prefix} — enriched {len(jobs)} job(s) ({sponsored} with visa/relocation support)", 0

    try:
        raise_if_cancelled()
        existing = list(company.get("matching_jobs") or [])
        all_scraped = await fetch_board(client, company, save_fn=save_fn)
        title_matched = filter_relevant_jobs(all_scraped, True)
        scraped, _location_skipped = filter_jobs_by_expected_locations(
            title_matched, company, catalog_country=catalog_country,
        )
        raise_if_cancelled()
        jobs, preserved, new_count, stale_kept = merge_matching_jobs(existing, scraped)
        if enrich_board is not None:
            jobs = await enrich_board(
                client, jobs, company,
                only_missing=True,
                concurrency=enrich_concurrency,
            )
        company["matching_jobs"] = jobs
        company["updated"] = now_iso()
        company.pop("fetch_problem", None)
        company.pop("fetch_problem_date", None)
        company["fetch_ok"] = True
        company["fetch_ok_date"] = _today()
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        parts = [f"{len(jobs)} matching job(s)"]
        if sponsored:
            parts.append(f"{sponsored} with visa/relocation support")
        if preserved:
            parts.append(f"{preserved} preserved")
        if new_count:
            parts.append(f"{new_count} new")
        if stale_kept:
            parts.append(f"{stale_kept} kept from cache")
        _persist(company, save_fn)
        return f"{prefix} — {', '.join(parts)}", new_count
    except FetchCancelled:
        raise
    except Exception as exc:
        company["fetch_problem"] = True
        company["fetch_problem_date"] = _today()
        company["fetch_ok"] = False
        company.pop("fetch_ok_date", None)
        _persist(company, save_fn)
        return f"{prefix} — Error: {exc}", 0
