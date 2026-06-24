from __future__ import annotations

from collections.abc import Awaitable, Callable

from relocation_jobs.v2.catalog.repo import get_company
from relocation_jobs.v2.catalog.repo import sync_company_board_to_catalog
from relocation_jobs.v2.fetch import service as fetch_service
from relocation_jobs.v2.scrape.company import process_company

FetchBoard = Callable[..., Awaitable[list[dict]]]
EnrichBoard = Callable[..., Awaitable[list[dict]]]


async def fetch_and_persist_company(
    client,
    country_key: str,
    company_name: str,
    *,
    fetch_board: FetchBoard,
    enrich_board: EnrichBoard | None = None,
    enrich_only: bool = False,
    skip_enriched: bool = False,
    enrich_concurrency: int = 4,
    fetch_run_id: int | None = None,
) -> tuple[str, int]:
    company = get_company(country_key, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    def persist_board() -> None:
        sync_company_board_to_catalog(country_key, company)

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
            fetch_board=fetch_board,
            enrich_board=enrich_board,
            save_fn=persist_board,
            enrich_only=enrich_only,
            skip_enriched=skip_enriched,
            enrich_concurrency=enrich_concurrency,
            catalog_country=country_key,
        )

    return await fetch_service.fetch_company(
        client,
        company,
        1,
        1,
        country_key=country_key,
        process_company=process,
        save_fn=persist_board,
        enrich_only=enrich_only,
        skip_enriched=skip_enriched,
        enrich_concurrency=enrich_concurrency,
        fetch_run_id=fetch_run_id,
    )
