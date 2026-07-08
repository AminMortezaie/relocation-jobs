from __future__ import annotations

from relocation_jobs.catalog.repo import get_company
from relocation_jobs.catalog.repo import sync_company_board_to_catalog
from relocation_jobs.fetch import service as fetch_service
from relocation_jobs.fetch.ports import (
    BoardEnricher,
    BoardFetcher,
    OnCompanyResult,
    OnReview,
)
from relocation_jobs.scrape.board import fetch_ats_board
from relocation_jobs.scrape.company import process_company
from relocation_jobs.scrape.enrich import enrich_jobs


async def fetch_and_persist_company(
    client,
    country_key: str,
    company_name: str,
    *,
    fetch_board: BoardFetcher | None = None,
    enrich_board: BoardEnricher | None = None,
    enrich_only: bool = False,
    skip_enriched: bool = False,
    enrich_concurrency: int = 8,
    fetch_run_id: int | None = None,
    review_mode: bool = False,
    on_review: OnReview = None,
    on_company_result: OnCompanyResult = None,
) -> tuple[str, int]:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    def sync_board() -> None:
        sync_company_board_to_catalog(country_key, company)

    board_fetch: BoardFetcher = fetch_board or fetch_ats_board
    board_enrich: BoardEnricher = enrich_board if enrich_board is not None else enrich_jobs

    async def _fetch_board(proc_client, proc_company: dict, **kwargs) -> list[dict]:
        return await board_fetch(
            proc_client,
            proc_company,
            sync_board=sync_board,
            **kwargs,
        )

    async def process(
        proc_client,
        proc_company: dict,
        index: int,
        total: int,
        **kwargs,
    ) -> tuple[str, int]:
        return await process_company(
            proc_client,
            proc_company,
            index,
            total,
            fetch_board=_fetch_board,
            enrich_board=board_enrich,
            sync_board=sync_board,
            enrich_only=enrich_only,
            skip_enriched=skip_enriched,
            enrich_concurrency=enrich_concurrency,
            catalog_country=country_key,
            review_mode=review_mode,
            on_review=on_review,
            on_company_result=on_company_result,
        )

    return await fetch_service.fetch_company(
        client,
        company,
        1,
        1,
        country_key=country_key,
        process_company=process,
        sync_board=sync_board,
        enrich_only=enrich_only,
        skip_enriched=skip_enriched,
        enrich_concurrency=enrich_concurrency,
        fetch_run_id=fetch_run_id,
    )
