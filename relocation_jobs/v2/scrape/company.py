from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from relocation_jobs.core.location_tags import filter_jobs_by_expected_locations
from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.v2.scrape.filter import filter_relevant_jobs
from relocation_jobs.v2.scrape.merge import merge_matching_jobs, now_iso
from relocation_jobs.v2.shared.predicates import any_of

FetchBoard = Callable[..., Awaitable[list[dict]]]
EnrichBoard = Callable[..., Awaitable[list[dict]]]


@dataclass(frozen=True)
class _ScrapeLineContext:
    job_count: int
    sponsored: int
    preserved: int
    new_count: int
    stale_kept: int


@dataclass(frozen=True)
class _EnrichContext:
    prefix: str
    jobs: list[dict]
    enrich_board: EnrichBoard | None


@dataclass(frozen=True)
class _ProcessContext:
    enrich_only: bool


_SCRAPE_SUMMARY_PARTS: tuple[Callable[[_ScrapeLineContext], str | None], ...] = (
    lambda ctx: f"{ctx.sponsored} with visa/relocation support" if ctx.sponsored else None,
    lambda ctx: f"{ctx.preserved} preserved" if ctx.preserved else None,
    lambda ctx: f"{ctx.new_count} new" if ctx.new_count else None,
    lambda ctx: f"{ctx.stale_kept} kept from cache" if ctx.stale_kept else None,
)

_ENRICH_EARLY_EXIT: tuple[
    tuple[Callable[[_EnrichContext], bool], Callable[[_EnrichContext], tuple[str, int]]],
    ...,
] = (
    (
        lambda ctx: not ctx.jobs,
        lambda ctx: (f"{ctx.prefix} — no jobs to enrich", 0),
    ),
    (
        lambda ctx: ctx.enrich_board is None,
        lambda ctx: (f"{ctx.prefix} — enrich not configured", 0),
    ),
)

_SKIP_POST_SCRAPE_ENRICH: tuple[Callable[[EnrichBoard | None], bool], ...] = (
    lambda board: board is None,
)

_PROCESS_ENRICH_ONLY: tuple[Callable[[_ProcessContext], bool], ...] = (
    lambda ctx: ctx.enrich_only,
)


def _today() -> str:
    return date.today().isoformat()


def _company_line(company: dict, index: int, total: int) -> str:
    name = company.get("name") or ""
    city = company.get("city", "?")
    return f"[{index}/{total}] {name} ({city})"


def _persist_board(save_fn) -> None:
    if save_fn:
        save_fn()


def _sponsored_count(jobs: list[dict]) -> int:
    return sum(1 for job in jobs if job.get("visa_sponsorship") is True)


def _mark_fetch_ok(company: dict) -> None:
    company.pop("fetch_problem", None)
    company.pop("fetch_problem_date", None)
    company["fetch_ok"] = True
    company["fetch_ok_date"] = _today()


def _mark_fetch_failed(company: dict) -> None:
    company["fetch_problem"] = True
    company["fetch_problem_date"] = _today()
    company["fetch_ok"] = False
    company.pop("fetch_ok_date", None)


def _scrape_success_line(
    prefix: str,
    jobs: list[dict],
    *,
    preserved: int,
    new_count: int,
    stale_kept: int,
) -> str:
    ctx = _ScrapeLineContext(
        job_count=len(jobs),
        sponsored=_sponsored_count(jobs),
        preserved=preserved,
        new_count=new_count,
        stale_kept=stale_kept,
    )
    parts = [f"{ctx.job_count} matching job(s)"]
    parts.extend(part for rule in _SCRAPE_SUMMARY_PARTS if (part := rule(ctx)))
    return f"{prefix} — {', '.join(parts)}"


def _enrich_early_exit(ctx: _EnrichContext) -> tuple[str, int] | None:
    for matches, outcome in _ENRICH_EARLY_EXIT:
        if matches(ctx):
            return outcome(ctx)
    return None


async def _filter_board_listings(
    client,
    company: dict,
    *,
    fetch_board: FetchBoard,
    catalog_country: str,
    save_fn,
) -> list[dict]:
    raw = await fetch_board(client, company, save_fn=save_fn)
    title_matched = filter_relevant_jobs(raw, True)
    matched, _skipped = filter_jobs_by_expected_locations(
        title_matched, company, catalog_country=catalog_country,
    )
    return matched


async def _maybe_enrich_scraped_board(
    client,
    jobs: list[dict],
    company: dict,
    *,
    enrich_board: EnrichBoard | None,
    enrich_concurrency: int,
) -> list[dict]:
    if any_of(enrich_board, _SKIP_POST_SCRAPE_ENRICH):
        return jobs
    return await enrich_board(
        client, jobs, company,
        only_missing=True,
        concurrency=enrich_concurrency,
    )


async def enrich_company_board(
    client,
    company: dict,
    prefix: str,
    *,
    enrich_board: EnrichBoard | None,
    skip_enriched: bool,
    enrich_concurrency: int,
    save_fn,
) -> tuple[str, int]:
    ctx = _EnrichContext(
        prefix=prefix,
        jobs=company.get("matching_jobs") or [],
        enrich_board=enrich_board,
    )
    early = _enrich_early_exit(ctx)
    if early is not None:
        return early

    jobs = await enrich_board(
        client, ctx.jobs, company,
        only_missing=skip_enriched,
        concurrency=enrich_concurrency,
    )
    company["matching_jobs"] = jobs
    company["updated"] = now_iso()
    _persist_board(save_fn)
    sponsored = _sponsored_count(jobs)
    return (
        f"{prefix} — enriched {len(jobs)} job(s) ({sponsored} with visa/relocation support)",
        0,
    )


async def scrape_company_board(
    client,
    company: dict,
    prefix: str,
    *,
    fetch_board: FetchBoard,
    enrich_board: EnrichBoard | None,
    enrich_concurrency: int,
    catalog_country: str,
    save_fn,
) -> tuple[str, int]:
    raise_if_cancelled()
    existing = list(company.get("matching_jobs") or [])
    scraped = await _filter_board_listings(
        client, company,
        fetch_board=fetch_board,
        catalog_country=catalog_country,
        save_fn=save_fn,
    )
    raise_if_cancelled()
    jobs, preserved, new_count, stale_kept = merge_matching_jobs(existing, scraped)
    jobs = await _maybe_enrich_scraped_board(
        client, jobs, company,
        enrich_board=enrich_board,
        enrich_concurrency=enrich_concurrency,
    )
    company["matching_jobs"] = jobs
    company["updated"] = now_iso()
    _mark_fetch_ok(company)
    _persist_board(save_fn)
    return _scrape_success_line(
        prefix, jobs,
        preserved=preserved,
        new_count=new_count,
        stale_kept=stale_kept,
    ), new_count


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
    company["updated"] = now_iso()
    prefix = _company_line(company, index, total)
    mode_ctx = _ProcessContext(enrich_only=enrich_only)

    if any_of(mode_ctx, _PROCESS_ENRICH_ONLY):
        return await enrich_company_board(
            client, company, prefix,
            enrich_board=enrich_board,
            skip_enriched=skip_enriched,
            enrich_concurrency=enrich_concurrency,
            save_fn=save_fn,
        )

    try:
        return await scrape_company_board(
            client, company, prefix,
            fetch_board=fetch_board,
            enrich_board=enrich_board,
            enrich_concurrency=enrich_concurrency,
            catalog_country=catalog_country,
            save_fn=save_fn,
        )
    except FetchCancelled:
        raise
    except Exception as exc:
        _mark_fetch_failed(company)
        _persist_board(save_fn)
        return f"{prefix} — Error: {exc}", 0
