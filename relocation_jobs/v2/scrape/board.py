from __future__ import annotations

from collections.abc import Awaitable, Callable

from relocation_jobs.core.ats_constants import ATS_TYPE_CHOICES
from relocation_jobs.v2.scrape.boards.ashby import fetch_ashby_board
from relocation_jobs.v2.scrape.boards.bol import fetch_bol_board
from relocation_jobs.v2.scrape.boards.deel import fetch_deel_board
from relocation_jobs.v2.scrape.ats_resolve import ensure_company_ats
from relocation_jobs.v2.scrape.boards.generic import fetch_generic_board
from relocation_jobs.v2.scrape.boards.greenhouse import fetch_greenhouse_board
from relocation_jobs.v2.scrape.boards.http_sync import (
    fetch_applytojob_board,
    fetch_bamboo_board,
    fetch_epam_board,
    fetch_hirehive_board,
    fetch_movingimage_board,
    fetch_project_a_board,
    fetch_rss_board,
)
from relocation_jobs.v2.scrape.boards.job_shop import fetch_job_shop_board
from relocation_jobs.v2.scrape.boards.join import fetch_join_board
from relocation_jobs.v2.scrape.boards.lever import fetch_lever_board
from relocation_jobs.v2.scrape.boards.personio import fetch_personio_board
from relocation_jobs.v2.scrape.boards.playwright_ats import (
    fetch_atlassian_board,
    fetch_jibe_board,
)
from relocation_jobs.v2.scrape.boards.recruitee import fetch_recruitee_board
from relocation_jobs.v2.scrape.boards.smartrecruiters import fetch_smartrecruiters_board
from relocation_jobs.v2.scrape.boards.teamtailor import fetch_teamtailor_board
from relocation_jobs.v2.scrape.boards.workable import fetch_workable_board
from relocation_jobs.v2.scrape.boards.workday import fetch_workday_board

BoardFetcher = Callable[..., Awaitable[list[dict]]]

_BOARD_FETCHERS: dict[str, BoardFetcher] = {
    "ashby": fetch_ashby_board,
    "atlassian": fetch_atlassian_board,
    "applicably": fetch_applytojob_board,
    "bamboo": fetch_bamboo_board,
    "bol": fetch_bol_board,
    "deel": fetch_deel_board,
    "epam": fetch_epam_board,
    "greenhouse": fetch_greenhouse_board,
    "greenhouse_eu": fetch_greenhouse_board,
    "hirehive": fetch_hirehive_board,
    "jibe": fetch_jibe_board,
    "job_shop": fetch_job_shop_board,
    "join": fetch_join_board,
    "lever": fetch_lever_board,
    "lever_eu": fetch_lever_board,
    "movingimage": fetch_movingimage_board,
    "personio": fetch_personio_board,
    "project_a": fetch_project_a_board,
    "recruitee": fetch_recruitee_board,
    "rss": fetch_rss_board,
    "smartrecruiters": fetch_smartrecruiters_board,
    "teamtailor": fetch_teamtailor_board,
    "workable": fetch_workable_board,
    "workday": fetch_workday_board,
}

_SUPPORTED_ATS = frozenset(_BOARD_FETCHERS)
_GENERIC_ATS = frozenset({"", "generic"})


class UnsupportedAtsTypeError(LookupError):
    def __init__(self, ats_type: str):
        self.ats_type = ats_type
        super().__init__(f"Unsupported ATS type for v2 board fetch: {ats_type or 'unknown'}")


def supported_ats_types() -> frozenset[str]:
    return _SUPPORTED_ATS


def assert_full_ats_coverage() -> None:
    missing = {key for key, _ in ATS_TYPE_CHOICES} - _SUPPORTED_ATS
    if missing:
        raise RuntimeError(f"v2 board fetch missing ATS types: {sorted(missing)}")


async def fetch_ats_board(
    client,
    company: dict,
    *,
    persist_board=None,
    **kwargs,
) -> list[dict]:
    await ensure_company_ats(client, company, persist_board=persist_board)
    ats_type = (company.get("ats_type") or "").strip().lower()
    board_url = (company.get("ats_url") or company.get("careers_url") or "").strip()
    if not board_url:
        raise LookupError(f"No careers or ATS URL for {company.get('name') or 'company'}")

    if ats_type in _GENERIC_ATS:
        return await fetch_generic_board(client, board_url, company)

    fetcher = _BOARD_FETCHERS.get(ats_type)
    if fetcher is not None:
        return await fetcher(client, board_url, company)

    raise UnsupportedAtsTypeError(ats_type)
