from __future__ import annotations

from collections.abc import Awaitable, Callable

from relocation_jobs.v2.scrape.boards.greenhouse import fetch_greenhouse_board

_SUPPORTED_ATS = frozenset({"greenhouse", "greenhouse_eu"})


class UnsupportedAtsTypeError(LookupError):
    def __init__(self, ats_type: str):
        self.ats_type = ats_type
        super().__init__(f"Unsupported ATS type for v2 board fetch: {ats_type or 'unknown'}")


async def fetch_ats_board(client, company: dict, **kwargs) -> list[dict]:
    ats_type = (company.get("ats_type") or "").strip().lower()
    board_url = (company.get("ats_url") or company.get("careers_url") or "").strip()
    if not board_url:
        raise LookupError(f"No careers or ATS URL for {company.get('name') or 'company'}")

    if ats_type in _SUPPORTED_ATS:
        return await fetch_greenhouse_board(client, board_url)

    if not ats_type:
        raise LookupError(
            f"No cached ATS type for {company.get('name') or 'company'} — detect ATS before fetch"
        )
    raise UnsupportedAtsTypeError(ats_type)
