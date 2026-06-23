"""Bulk scrape orchestration: per-company processing and CLI entry."""

from __future__ import annotations

import asyncio
import contextlib
import threading

from relocation_jobs.core.ats_constants import DEFAULT_CONCURRENCY, HTTPX_AVAILABLE
from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.core.location_tags import filter_jobs_by_expected_locations
from relocation_jobs.core.scrape_cancel import FetchCancelled, is_cancel_requested, raise_if_cancelled
from relocation_jobs.scrape import http as _scrape_http
from relocation_jobs.scrape.ipc import report_activity, report_progress, report_review_jobs, review_filtered_jobs
from relocation_jobs.scrape.listing import filter_relevant_jobs
from relocation_jobs.scrape.merge import backfill_listing_locations, merge_matching_jobs, now_iso
from relocation_jobs.scrape.shim_bind import scrape_jobs_shim
from relocation_jobs.scrape.util import safe_print, today

if HTTPX_AVAILABLE:
    httpx = _scrape_http.httpx

DEFAULT_WORKERS = DEFAULT_CONCURRENCY


def _company_ats_type(company: dict) -> str:
    return (company.get("ats_type") or "").strip() or "generic"


async def process_company_async(
    client: httpx.AsyncClient,
    company: dict,
    index: int,
    total: int,
    *,
    save_fn,
    enrich_only: bool,
    skip_enriched: bool,
    enrich_concurrency: int,
    review_mode: bool = False,
    catalog_country: str = "",
) -> tuple[str, int]:
    name = company["name"]
    city = company.get("city", "?")
    prefix = f"[{index}/{total}] {name} ({city})"
    company["updated"] = now_iso()

    if enrich_only:
        jobs = company.get("matching_jobs") or []
        if not jobs:
            return f"{prefix} — no jobs to enrich", 0
        sj = scrape_jobs_shim()
        jobs = await sj.enrich_jobs_async_with_client(
            client, jobs, company,
            only_missing=skip_enriched,
            concurrency=enrich_concurrency,
            preserve_fetched=True,
        )
        company["matching_jobs"] = jobs
        company["updated"] = now_iso()
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        return (
            f"{prefix} — enriched {len(jobs)} job(s) "
            f"({sponsored} with visa/relocation support)",
            0,
        )

    try:
        raise_if_cancelled()
        sj = scrape_jobs_shim()
        existing = list(company.get("matching_jobs") or [])
        all_scraped = await sj.get_jobs_async(
            client, company, save_fn=save_fn, relevant_only=False
        )
        title_matched = filter_relevant_jobs(all_scraped, True)
        scraped, location_filtered = filter_jobs_by_expected_locations(
            title_matched,
            company,
            catalog_country=catalog_country,
        )
        if location_filtered:
            print(
                f"    Skipped {len(location_filtered)} role(s) — "
                "location outside company office tags"
            )
        if review_mode:
            filtered_out = review_filtered_jobs(
                all_scraped,
                scraped,
                company,
                catalog_country=catalog_country,
            )
            report_review_jobs(included=scraped, filtered=filtered_out)
        raise_if_cancelled()
        jobs, preserved, new_count, stale_kept = merge_matching_jobs(existing, scraped)
        backfill_listing_locations(jobs, title_matched)
        report_activity("Checking visa/relocation details…")
        jobs = await sj.enrich_jobs_async_with_client(
            client, jobs, company,
            only_missing=True,
            concurrency=enrich_concurrency,
            preserve_fetched=True,
        )
        company["matching_jobs"] = jobs
        company["updated"] = now_iso()
        if company.get("fetch_problem"):
            company.pop("fetch_problem", None)
            company.pop("fetch_problem_date", None)
        company["fetch_ok"] = True
        company["fetch_ok_date"] = today()
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        applied_n = sum(1 for j in jobs if j.get("applied"))
        extra = []
        if preserved:
            extra.append(f"{preserved} preserved")
        if new_count:
            extra.append(f"{new_count} new")
        if stale_kept:
            extra.append(f"{stale_kept} kept from cache")
        if applied_n:
            extra.append(f"{applied_n} applied")
        suffix = f" ({', '.join(extra)})" if extra else ""
        return (
            f"{prefix} — {len(jobs)} matching job(s) "
            f"({sponsored} with visa/relocation support){suffix}",
            new_count,
        )
    except FetchCancelled:
        raise
    except Exception as e:
        if not company.get("matching_jobs"):
            company["matching_jobs"] = []
        company["updated"] = now_iso()
        return f"{prefix} — Error: {e}", 0


async def run_file_async(
    country_key: str,
    *,
    target: str | None = None,
    skip_filled: bool = False,
    enrich_only: bool = False,
    skip_enriched: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
    ats_type: str | None = None,
) -> None:
    sj = scrape_jobs_shim()
    if not sj.HTTPX_AVAILABLE:
        raise SystemExit("httpx is required for async scraping: pip install httpx")

    data = sj.load_country_catalog(country_key) or {"companies": []}

    file_lock = threading.Lock()

    def checkpoint_company(company: dict) -> None:
        with file_lock:
            sj.upsert_company(
                country_key,
                company,
                updated=company.get("updated") or now_iso(),
            )

    def finalize_catalog() -> None:
        report_progress(current=work_total, total=work_total, status="saving")
        with file_lock:
            ts = now_iso()
            sj.touch_country_meta(
                country_key,
                updated=ts,
                jobs_fetched=ts,
                total=len(data.get("companies") or []),
            )
        report_progress(current=work_total, total=work_total, status="done")

    companies = data["companies"]
    if ats_type:
        companies = [c for c in companies if _company_ats_type(c) == ats_type]
        if not companies:
            msg = f"No companies with ATS '{ats_type}' in {country_key}"
            print(msg)
            raise LookupError(msg)
    if target:
        companies = [c for c in companies if c["name"].lower() == target.lower()]
        if not companies:
            msg = f"Company '{target}' not found in {country_key}"
            print(msg)
            raise LookupError(msg)

    work: list[tuple[dict, int]] = []
    total = len(companies)
    for i, company in enumerate(companies, 1):
        if skip_filled and company.get("matching_jobs") and not enrich_only:
            safe_print(
                f"[{i}/{total}] {company['name']} — skipped "
                f"(already has {len(company['matching_jobs'])} jobs)"
            )
            continue
        work.append((company, i))

    if target:
        print(f"\n=== {target} ===")
    elif ats_type:
        print(
            f"\n=== {country_key} · {ats_type} ({len(work)} to process, "
            f"{concurrency} concurrent, asyncio) ==="
        )
    else:
        print(
            f"\n=== {country_key} ({len(work)} to process, "
            f"{concurrency} concurrent, asyncio) ==="
        )

    if not work:
        if target:
            company = next(
                (c for c in data["companies"] if c["name"].lower() == target.lower()),
                None,
            )
            if company and company.get("matching_jobs"):
                n = len(company["matching_jobs"])
                print(f"Done {target} — skipped (already has {n} matching job(s))")
            else:
                print(f"Done {target} — nothing to process")
        elif ats_type:
            scope = f"{country_key} · {ats_type}"
            print(f"Done {scope} — no companies to process (all skipped or already filled)")
        else:
            total_jobs = sum(len(c.get("matching_jobs", [])) for c in data["companies"])
            print(
                f"Done {country_key} — {total_jobs} matching jobs "
                f"across {len(data['companies'])} companies."
            )
        return

    work_total = len(work)
    progress = {"completed": 0}
    progress_lock = asyncio.Lock()
    report_progress(current=0, total=work_total, status="starting")

    enrich_concurrency = max(4, min(12, concurrency * 2))
    sem = asyncio.Semaphore(max(1, concurrency))

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency),
    ) as client:

        async def bounded(item: tuple[dict, int]) -> str | None:
            company, idx = item
            name = company["name"]
            if is_cancel_requested():
                return None
            report_progress(
                current=progress["completed"],
                total=work_total,
                company=name,
                status="fetching",
            )
            new_count = 0
            try:
                async with sem:
                    raise_if_cancelled()
                    msg, new_count = await process_company_async(
                        client, company, idx, total,
                        save_fn=None,
                        enrich_only=enrich_only,
                        skip_enriched=skip_enriched,
                        enrich_concurrency=enrich_concurrency,
                        review_mode=bool(target),
                        catalog_country=country_key or "",
                    )
            except FetchCancelled:
                return None
            except asyncio.CancelledError:
                if is_cancel_requested():
                    return None
                raise
            safe_print(msg)
            async with progress_lock:
                progress["completed"] += 1
                done = progress["completed"]
            report_progress(
                current=done,
                total=work_total,
                company=name,
                status="done",
                new_jobs=new_count,
            )
            if is_cancel_requested():
                return None
            await asyncio.to_thread(checkpoint_company, company)
            return msg

        async def cancel_watcher(tasks: list[asyncio.Task]) -> None:
            while not is_cancel_requested():
                await asyncio.sleep(0.15)
            for task in tasks:
                if not task.done():
                    task.cancel()

        if concurrency <= 1:
            for item in work:
                if is_cancel_requested():
                    safe_print("Cancelled — saved progress for completed companies")
                    finalize_catalog()
                    raise SystemExit(130)
                await bounded(item)
        else:
            queue: asyncio.Queue[tuple[dict, int]] = asyncio.Queue()
            for item in work:
                queue.put_nowait(item)

            async def worker() -> None:
                while True:
                    if is_cancel_requested():
                        return
                    try:
                        item = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    await bounded(item)

            n_workers = min(concurrency, len(work))
            workers = [asyncio.create_task(worker()) for _ in range(n_workers)]
            watcher = asyncio.create_task(cancel_watcher(workers))
            try:
                await asyncio.gather(*workers, return_exceptions=True)
            finally:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher
            if is_cancel_requested():
                safe_print("Cancelled — saved progress for completed companies")
                finalize_catalog()
                raise SystemExit(130)

    finalize_catalog()
    if target:
        company = work[0][0]
        jobs = company.get("matching_jobs") or []
        sponsored = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
        print(
            f"Done {target} — {len(jobs)} matching job(s) "
            f"({sponsored} with visa/relocation support)"
        )
    else:
        total_jobs = sum(len(c.get("matching_jobs", [])) for c in data["companies"])
        print(
            f"Done {country_key} — {total_jobs} matching jobs "
            f"across {len(data['companies'])} companies."
        )

