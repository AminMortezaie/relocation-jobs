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
        import relocation_jobs.scrape.enrich as enrich_mod

        original = enrich_mod.fetch_job_description_async
        try:
            enrich_mod.fetch_job_description_async = fake_fetch
            out = await enrich_jobs(client, jobs, company, only_missing=False, concurrency=1)
        finally:
            enrich_mod.fetch_job_description_async = original

    assert out[0]["visa_sponsorship"] is True
    assert out[0]["fetched"]
    assert out[0]["description_text"] == "visa sponsorship available for qualified applicants"


@pytest.mark.asyncio
async def test_enrich_only_missing_skips_when_visa_description_and_location_present():
    from relocation_jobs.scrape.enrich import enrich_jobs

    jobs = [
        {
            "title": "Engineer",
            "url": "https://example.com/jobs/1",
            "visa_sponsorship": True,
            "description_text": "Existing JD text.",
            "location": "Berlin, Germany",
            "fetched": "2025-01-15",
        },
    ]
    company = {"name": "Acme", "ats_type": "generic"}

    async def fake_fetch(_client, url, ats_type=None):
        raise AssertionError("should not fetch when visa, description, and location exist")

    import httpx

    async with httpx.AsyncClient() as client:
        import relocation_jobs.scrape.enrich as enrich_mod

        original = enrich_mod.fetch_job_description_async
        try:
            enrich_mod.fetch_job_description_async = fake_fetch
            out = await enrich_jobs(client, jobs, company, only_missing=True, concurrency=1)
        finally:
            enrich_mod.fetch_job_description_async = original

    assert out[0]["description_text"] == "Existing JD text."
    assert out[0]["location"] == "Berlin, Germany"


@pytest.mark.asyncio
async def test_enrich_only_missing_fetches_when_location_missing():
    from relocation_jobs.scrape.enrich import enrich_jobs

    jobs = [
        {
            "title": "Engineer",
            "url": "https://example.com/jobs/1",
            "visa_sponsorship": True,
            "description_text": "Existing JD text.",
            "fetched": "2025-01-15",
        },
    ]
    company = {"name": "Acme", "ats_type": "generic"}

    async def fake_fetch(_client, url, ats_type=None):
        return "Updated JD with visa sponsorship."

    import httpx

    async with httpx.AsyncClient() as client:
        import relocation_jobs.scrape.enrich as enrich_mod

        original = enrich_mod.fetch_job_description_async
        try:
            enrich_mod.fetch_job_description_async = fake_fetch
            out = await enrich_jobs(client, jobs, company, only_missing=True, concurrency=1)
        finally:
            enrich_mod.fetch_job_description_async = original

    assert "Updated JD" in out[0]["description_text"]
    assert not out[0].get("location")


@pytest.mark.asyncio
async def test_enrich_only_missing_fetches_when_description_missing():
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

    async def fake_fetch(_client, url, ats_type=None):
        return "Updated role requirements and visa sponsorship."

    import httpx

    async with httpx.AsyncClient() as client:
        import relocation_jobs.scrape.enrich as enrich_mod

        original = enrich_mod.fetch_job_description_async
        try:
            enrich_mod.fetch_job_description_async = fake_fetch
            out = await enrich_jobs(client, jobs, company, only_missing=True, concurrency=1)
        finally:
            enrich_mod.fetch_job_description_async = original

    assert "Updated role requirements" in out[0]["description_text"]


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
