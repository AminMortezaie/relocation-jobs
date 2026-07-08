from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Optional, Protocol


class BoardFetcher(Protocol):
    async def __call__(
        self,
        client,
        company: dict,
        **kwargs,
    ) -> list[dict]: ...


class BoardEnricher(Protocol):
    async def __call__(
        self,
        client,
        company: dict,
        jobs: list[dict],
        **kwargs,
    ) -> list[dict]: ...


class SyncBoardToCatalog(Protocol):
    def __call__(self) -> None: ...


class ReviewCallback(Protocol):
    def __call__(self, payload: dict) -> None: ...


class CompanyResultCallback(Protocol):
    def __call__(self, company_name: str, new_count: int, jobs: list[dict]) -> None: ...


OnReview = Optional[ReviewCallback]
OnCompanyResult = Optional[CompanyResultCallback]
ProcessCompany = Callable[..., Awaitable[tuple[str, int]]]
