from __future__ import annotations

import json
from pathlib import Path

import pytest

from relocation_jobs.companies.service import detect_ats_for_company
from relocation_jobs.scrape.ats_resolve import apply_known_ats_override
from relocation_jobs.scrape.boards.hibob import (
    fetch_hibob_board,
    hibob_job_id_from_url,
    parse_hibob_jobs,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ats" / "hibob_job_ads.json"


def test_detect_mobile_de_as_hibob():
    ats_type, ats_url = detect_ats_for_company(
        "Mobile.de",
        "https://mobilede.careers.hibob.com/jobs",
    )
    assert ats_type == "hibob"
    assert ats_url == "https://mobilede.careers.hibob.com/jobs"


def test_apply_known_ats_override_fixes_cached_generic_for_mobile_de():
    company = {
        "name": "Mobile.de",
        "careers_url": "https://mobilede.careers.hibob.com/jobs",
        "ats_type": "generic",
        "ats_url": "",
    }
    apply_known_ats_override(company)
    assert company["ats_type"] == "hibob"
    assert company["ats_url"] == "https://mobilede.careers.hibob.com/jobs"


def test_parse_hibob_jobs():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    jobs = parse_hibob_jobs(payload, "mobilede")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Principal Engineer (d/f/m)"
    assert jobs[0]["location"] == "Berlin, Germany"
    assert jobs[0]["url"] == (
        "https://mobilede.careers.hibob.com/jobs/0413848d-1163-4682-a260-0d024ff9b031"
    )
    assert "Build platform services." in jobs[0]["description_text"]


def test_hibob_job_id_from_url():
    url = "https://mobilede.careers.hibob.com/jobs/0413848d-1163-4682-a260-0d024ff9b031"
    assert hibob_job_id_from_url(url) == "0413848d-1163-4682-a260-0d024ff9b031"


@pytest.mark.asyncio
async def test_fetch_hibob_board_uses_payload_fetcher():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def fake_fetch(_page_url: str):
        return payload

    import httpx

    async with httpx.AsyncClient() as client:
        jobs = await fetch_hibob_board(
            client,
            "https://mobilede.careers.hibob.com/jobs",
            {"careers_url": "https://mobilede.careers.hibob.com/jobs"},
            payload_fetcher=fake_fetch,
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Principal Engineer (d/f/m)"
