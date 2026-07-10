from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relocation_jobs.fetch.country_runner import run_country_fetch


@pytest.mark.asyncio
async def test_company_timeout_does_not_cancel_remaining_companies(db, monkeypatch):
    del db
    monkeypatch.setenv("FETCH_COMPANY_TIMEOUT_SECONDS", "1")

    companies = [{"name": "FastCo"}, {"name": "SlowCo"}]
    cancel_calls: list[int] = []
    logs: list[str] = []

    monkeypatch.setattr(
        "relocation_jobs.fetch.country_runner.list_country_company_stubs",
        lambda country_key: companies,
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.country_runner.get_company",
        lambda country_key, name: {"name": name, "careers_url": f"https://{name}.example/jobs"},
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.country_runner.load_country_catalog",
        lambda country_key: {"companies": companies},
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.country_runner.patch_country_catalog_meta",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.country_runner.fetch_repo.fetch_run_cancel_requested",
        lambda run_id: False,
    )
    monkeypatch.setattr(
        "relocation_jobs.fetch.country_runner.fetch_repo.request_fetch_run_cancel",
        lambda run_id: cancel_calls.append(run_id),
    )

    async def fake_fetch(client, country_key, name, **kwargs):
        if name == "SlowCo":
            await asyncio.sleep(2)
            return f"[1/1] {name} — ok", 0
        return f"[1/1] {name} — ok", 0

    monkeypatch.setattr(
        "relocation_jobs.fetch.country_runner.fetch_and_persist_company",
        AsyncMock(side_effect=fake_fetch),
    )

    client = MagicMock()
    new_jobs, done, cancelled = await run_country_fetch(
        client,
        "uk",
        run_id=7,
        concurrency=1,
        on_log=logs.append,
    )

    assert cancelled is False
    assert done == 2
    assert cancel_calls == []
    assert any("SlowCo" in line and "timed out" in line for line in logs)
    assert any("FastCo" in line for line in logs)
