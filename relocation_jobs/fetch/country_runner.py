from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from relocation_jobs.core.scrape_cancel import FetchCancelled, clear_cancel_checker, set_cancel_checker
from relocation_jobs.catalog.repo import (
    get_company,
    list_country_company_stubs,
    load_country_catalog,
    patch_country_catalog_meta,
)
from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.fetch.log import log_event
from relocation_jobs.fetch.pipeline import fetch_and_persist_company
from relocation_jobs.scrape.merge import now_iso


def _companies_to_fetch(
    country_key: str,
    *,
    skip_filled: bool,
    ats_type: str | None,
) -> list[dict]:
    companies = list_country_company_stubs(country_key)
    if not companies:
        raise LookupError(f"No catalog for country: {country_key}")
    if ats_type:
        want = ats_type.strip().lower()
        companies = [c for c in companies if (c.get("ats_type") or "").strip().lower() == want]
        if not companies:
            raise LookupError(f"No companies with ATS '{ats_type}' in {country_key}")
    if skip_filled:
        companies = [c for c in companies if not c.get("has_jobs")]
    return companies


def _per_worker_limits(country_workers: int) -> tuple[int, int]:
    workers = max(1, country_workers)
    limit = min(16, max(12, 192 // workers))
    return limit, limit


def _cancel_checker(run_id: int) -> Callable[[], bool]:
    cache = {"at": 0.0, "value": False}

    def check() -> bool:
        now = time.monotonic()
        if now - cache["at"] < 1.0:
            return cache["value"]
        cache["value"] = fetch_repo.fetch_run_cancel_requested(run_id)
        cache["at"] = now
        return cache["value"]

    return check


def _fetch_one_thread(
    country_key: str,
    name: str,
    index: int,
    total: int,
    *,
    run_id: int,
    http_concurrency: int,
    enrich_concurrency: int,
) -> tuple[str, int, bool, str | None]:
    """Run a single company fetch in its own thread with its own event loop.

    Returns (name, new_jobs, was_cancelled, log_message).
    """
    check_cancel = _cancel_checker(run_id)
    set_cancel_checker(check_cancel)
    try:
        if check_cancel():
            return name, 0, True, None
        company = get_company(country_key, name)
        if company is None:
            return name, 0, False, f"[{index}/{total}] {name} — skipped (not in catalog)"

        async def _inner():
            from relocation_jobs.fetch.runner import _make_fetch_client
            async with _make_fetch_client(concurrency=http_concurrency) as client:
                return await fetch_and_persist_company(
                    client, country_key, name, fetch_run_id=run_id,
                    enrich_concurrency=enrich_concurrency,
                )

        try:
            msg, new_count = asyncio.run(_inner())
            return name, new_count, False, msg
        except FetchCancelled:
            return name, 0, True, None
        except Exception as exc:
            return name, 0, False, f"[{index}/{total}] {name} — Error: {exc}"
    finally:
        clear_cancel_checker()


async def run_country_fetch(
    client,
    country_key: str,
    *,
    run_id: int,
    skip_filled: bool = False,
    ats_type: str | None = None,
    concurrency: int = 1,
    on_progress: Callable[[dict], None] | None = None,
    on_log: Callable[[str], None] | None = None,
) -> tuple[int, int, bool]:
    companies = _companies_to_fetch(
        country_key,
        skip_filled=skip_filled,
        ats_type=ats_type,
    )
    total = len(companies)
    workers = max(1, min(concurrency, total))
    http_concurrency, enrich_concurrency = _per_worker_limits(workers)

    def report(current: int, company_name: str | None, status: str) -> None:
        payload = {
            "current": current,
            "total": total,
            "company": company_name,
            "status": status,
        }
        if on_progress:
            on_progress(payload)

    set_cancel_checker(_cancel_checker(run_id))
    report(0, None, "starting")
    log_event(
        f"country fetch {country_key}: {total} companies, concurrency={workers}",
        enrich_concurrency=enrich_concurrency,
    )

    if workers <= 1:
        new_jobs_total = 0
        done = 0
        cancelled = False
        try:
            for index, stub in enumerate(companies, start=1):
                if fetch_repo.fetch_run_cancel_requested(run_id):
                    cancelled = True
                    break
                name = stub.get("name") or ""
                report(index - 1, name, "fetching")
                company = get_company(country_key, name)
                if company is None:
                    if on_log:
                        on_log(f"[{index}/{total}] {name} — skipped (not in catalog)")
                    done = index
                    continue
                try:
                    msg, new_count = await fetch_and_persist_company(
                        client, country_key, name, fetch_run_id=run_id,
                        enrich_concurrency=enrich_concurrency,
                    )
                    new_jobs_total += new_count
                    if on_log:
                        on_log(msg)
                except FetchCancelled:
                    cancelled = True
                    break
                except Exception as exc:
                    if on_log:
                        on_log(f"[{index}/{total}] {name} — Error: {exc}")
                done = index
                report(index, name, "done")
        finally:
            clear_cancel_checker()
    else:
        new_jobs_total = 0
        cancelled = False
        done = 0
        futures_map: dict = {}
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            company_iter = iter(enumerate(companies, start=1))
            in_flight = 0

            def _fill_pool():
                nonlocal in_flight
                while in_flight < workers:
                    if fetch_repo.fetch_run_cancel_requested(run_id):
                        return
                    item = next(company_iter, None)
                    if item is None:
                        return
                    index, stub = item
                    name = stub.get("name") or ""
                    f = pool.submit(
                        _fetch_one_thread,
                        country_key, name, index, total,
                        run_id=run_id,
                        http_concurrency=http_concurrency,
                        enrich_concurrency=enrich_concurrency,
                    )
                    futures_map[f] = (name, index)
                    f.add_done_callback(lambda _: None)
                    in_flight += 1

            _fill_pool()

            while futures_map:
                completed = next(as_completed(futures_map), None)
                if completed is None:
                    break
                fname, fidx = futures_map.pop(completed)
                in_flight -= 1
                try:
                    _, new_count, was_cancelled, msg = completed.result()
                    new_jobs_total += new_count
                    if was_cancelled:
                        cancelled = True
                    if msg and on_log:
                        on_log(msg)
                except Exception as exc:
                    if on_log:
                        on_log(f"[{fidx}/{total}] {fname} — Error: {exc}")
                done += 1
                report(done, fname, "done")
                if cancelled:
                    for f in futures_map:
                        f.cancel()
                    break
                _fill_pool()
        finally:
            clear_cancel_checker()
            pool.shutdown(wait=False, cancel_futures=True)

    ts = now_iso()
    refreshed = load_country_catalog(country_key) or {}
    patch_country_catalog_meta(
        country_key,
        updated=ts,
        jobs_fetched=ts,
        last_fetch_new_jobs=new_jobs_total,
        total=len(refreshed.get("companies") or []),
    )
    if not cancelled:
        report(total, None, "done")
    return new_jobs_total, done, cancelled
