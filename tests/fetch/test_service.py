from __future__ import annotations

import pytest

from relocation_jobs.fetch.repo import list_attempts
from relocation_jobs.fetch.types import AttemptStatus

FIXTURE_COMPANY = "Service OK Co"
FIXTURE_CAREERS_URL = "https://boards.greenhouse.io/service-ok"


@pytest.mark.asyncio
async def test_fetch_company_logs_success(db):
    from relocation_jobs.fetch import service as fetch_service

    async def fake_process(_client, company, _index, _total, **kwargs):
        company["matching_jobs"] = [{"url": "https://jobs.example/a", "title": "Eng"}]
        company["fetch_ok"] = True
        return f"[1/1] {FIXTURE_COMPANY} — 1 matching job(s)", 1

    company = {
        "name": FIXTURE_COMPANY,
        "careers_url": FIXTURE_CAREERS_URL,
    }
    msg, new_count = await fetch_service.fetch_company(
        None,
        company,
        1,
        1,
        country_key="uk",
        process_company=fake_process,
        sync_board=None,
        enrich_only=False,
        skip_enriched=False,
        enrich_concurrency=4,
    )
    assert new_count == 1
    assert "1 matching" in msg

    rows = list_attempts(country="uk", company_name=FIXTURE_COMPANY)
    assert len(rows) == 1
    assert rows[0].status == AttemptStatus.OK
    assert rows[0].jobs_new == 1


@pytest.mark.asyncio
async def test_fetch_company_logs_error_and_marks_problem(db):
    from relocation_jobs.fetch import service as fetch_service

    async def fake_process(_client, company, _index, _total, **kwargs):
        company["matching_jobs"] = []
        return f"[1/1] Fail Co — Error: connection refused", 0

    company = {"name": "Fail Co", "careers_url": "https://fail.example/jobs"}
    msg, new_count = await fetch_service.fetch_company(
        None,
        company,
        1,
        1,
        country_key="uk",
        process_company=fake_process,
        sync_board=None,
        enrich_only=False,
        skip_enriched=False,
        enrich_concurrency=4,
    )
    assert new_count == 0
    assert "Error:" in msg
    assert company.get("fetch_problem") is True
    assert company.get("fetch_problem_date")

    rows = list_attempts(country="uk", company_name="Fail Co")
    assert rows[0].status == AttemptStatus.ERROR
    assert rows[0].error_message == "connection refused"
