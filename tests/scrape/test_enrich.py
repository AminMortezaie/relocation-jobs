from __future__ import annotations

import pytest

from relocation_jobs.scrape.descriptions import detect_visa_relocation


def test_detect_visa_relocation_positive():
    text = "We offer visa sponsorship and relocation support for international candidates."
    assert detect_visa_relocation(text) is True


def test_detect_visa_relocation_negative():
    text = "Must be legally authorized to work. Open to candidates with existing work authorization only."
    assert detect_visa_relocation(text) is False


@pytest.mark.asyncio
async def test_enrich_jobs_sets_visa_from_description():
    from relocation_jobs.scrape.enrich import enrich_jobs

    jobs = [{"title": "Engineer", "url": "https://example.com/jobs/1"}]
    company = {"name": "Acme", "ats_type": "generic"}

    async def fake_fetch(_client, url, ats_type=None):
        assert url == "https://example.com/jobs/1"
        return "visa sponsorship available for qualified applicants"

    import httpx

    async with httpx.AsyncClient() as client:
        original = __import__(
            "relocation_jobs.scrape.enrich",
            fromlist=["fetch_job_description_async"],
        ).fetch_job_description_async
        try:
            import relocation_jobs.scrape.enrich as enrich_mod
            enrich_mod.fetch_job_description_async = fake_fetch
            out = await enrich_jobs(client, jobs, company, only_missing=False, concurrency=1)
        finally:
            enrich_mod.fetch_job_description_async = original

    assert out[0]["visa_sponsorship"] is True
    assert out[0]["fetched"]


@pytest.mark.asyncio
async def test_enrich_only_missing_does_not_overwrite_fetched():
    from relocation_jobs.scrape.enrich import enrich_jobs

    jobs = [
        {
            "title": "Engineer",
            "url": "https://example.com/jobs/1",
            "visa_sponsorship": True,
            "fetched": "2025-01-15",
        },
    ]
    company = {"name": "Acme", "ats_type": "generic"}

    import httpx

    async with httpx.AsyncClient() as client:
        out = await enrich_jobs(client, jobs, company, only_missing=True, concurrency=1)

    assert out[0]["fetched"] == "2025-01-15"


@pytest.mark.asyncio
async def test_enrich_missing_fetched_sets_today_without_overwriting_existing():
    from relocation_jobs.scrape.enrich import enrich_jobs

    jobs = [{"title": "Engineer", "url": "https://example.com/jobs/1"}]
    company = {"name": "Acme", "ats_type": "generic"}

    async def fake_fetch(_client, url, ats_type=None):
        return "visa sponsorship available"

    import httpx

    async with httpx.AsyncClient() as client:
        import relocation_jobs.scrape.enrich as enrich_mod

        original = enrich_mod.fetch_job_description_async
        try:
            enrich_mod.fetch_job_description_async = fake_fetch
            out = await enrich_jobs(client, jobs, company, only_missing=False, concurrency=1)
            assert out[0]["fetched"]
            jobs[0]["fetched"] = "2025-03-01"
            out2 = await enrich_jobs(client, jobs, company, only_missing=False, concurrency=1)
        finally:
            enrich_mod.fetch_job_description_async = original

    assert out2[0]["fetched"] == "2025-03-01"
