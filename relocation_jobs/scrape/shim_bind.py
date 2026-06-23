"""Lazy binding to the ``scrape_jobs`` shim (tests monkeypatch attributes there)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from relocation_jobs import scrape_jobs as ScrapeJobsShim


def scrape_jobs_shim() -> ScrapeJobsShim:
    from relocation_jobs import scrape_jobs as sj
    return sj
