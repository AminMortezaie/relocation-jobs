from __future__ import annotations

from collections.abc import Callable

from relocation_jobs.core.scrape_cancel import FetchCancelled, clear_cancel_checker, set_cancel_checker
from relocation_jobs.v2.catalog.repo import get_company, load_country_catalog, patch_country_catalog_meta
from relocation_jobs.v2.fetch import repo as fetch_repo
from relocation_jobs.v2.fetch.pipeline import fetch_and_persist_company
from relocation_jobs.v2.scrape.board import fetch_ats_board
from relocation_jobs.v2.scrape.merge import now_iso


def _company_ats_type(company: dict) -> str:
    return (company.get("ats_type") or "").strip().lower() or "generic"


def _companies_to_fetch(
    country_key: str,
    *,
    skip_filled: bool,
    ats_type: str | None,
) -> list[dict]:
    data = load_country_catalog(country_key)
    if not data:
        raise LookupError(f"No catalog for country: {country_key}")
    companies = list(data.get("companies") or [])
    if ats_type:
        want = ats_type.strip().lower()
        companies = [c for c in companies if _company_ats_type(c) == want]
        if not companies:
            raise LookupError(f"No companies with ATS '{ats_type}' in {country_key}")
    if skip_filled:
        companies = [c for c in companies if not (c.get("matching_jobs") or [])]
    return companies


async def run_country_fetch(
    client,
    country_key: str,
    *,
    run_id: int,
    skip_filled: bool = False,
    ats_type: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
    on_log: Callable[[str], None] | None = None,
) -> tuple[int, int, bool]:
    companies = _companies_to_fetch(
        country_key,
        skip_filled=skip_filled,
        ats_type=ats_type,
    )
    total = len(companies)
    new_jobs_total = 0
    done = 0
    cancelled = False

    def report(current: int, company_name: str | None, status: str) -> None:
        payload = {
            "current": current,
            "total": total,
            "company": company_name,
            "status": status,
        }
        if on_progress:
            on_progress(payload)

    set_cancel_checker(lambda: fetch_repo.fetch_run_cancel_requested(run_id))
    report(0, None, "starting")
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
                    client,
                    country_key,
                    name,
                    fetch_board=fetch_ats_board,
                    fetch_run_id=run_id,
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
