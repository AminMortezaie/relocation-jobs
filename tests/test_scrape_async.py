"""Async scraper tests using respx and pytest-asyncio."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from relocation_jobs import scrape_jobs as sj
from tests.helpers.http_mock import load_ats_fixture

pytestmark = pytest.mark.asyncio


@pytest.fixture
def httpx_client():
    return httpx.AsyncClient(headers=sj.HEADERS, follow_redirects=True)


@respx.mock
async def test_scrape_lever_async(httpx_client):
    payload = [
        {
            "text": "Backend Developer",
            "hostedUrl": "https://jobs.lever.co/acme/backend",
            "categories": {"location": "Berlin"},
        }
    ]
    respx.get("https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_lever_async(httpx_client, "https://jobs.lever.co/acme")
    assert jobs[0]["title"] == "Backend Developer"


@respx.mock
async def test_scrape_greenhouse_async(httpx_client):
    payload = load_ats_fixture("ashby.json")  # has jobs key? no - use greenhouse structure
    payload = {
        "jobs": [
            {
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Berlin"},
            }
        ]
    }
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_greenhouse_async(httpx_client, "https://boards.greenhouse.io/acme")
    assert jobs[0]["title"] == "Backend Engineer"


@respx.mock
async def test_scrape_ashby_async(httpx_client):
    payload = load_ats_fixture("ashby.json")
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_ashby_async(httpx_client, "https://jobs.ashbyhq.com/acme")
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_scrape_workable_async(httpx_client):
    payload = load_ats_fixture("workable.json")
    respx.post("https://apply.workable.com/api/v2/accounts/acme/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_workable_async(httpx_client, "https://apply.workable.com/acme/")
    assert jobs[0]["title"] == "Backend Software Engineer"


@respx.mock
async def test_scrape_recruitee_async(httpx_client):
    payload = load_ats_fixture("recruitee.json")
    respx.get("https://acme.recruitee.com/api/offers/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_recruitee_async(httpx_client, "https://acme.recruitee.com/")
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_scrape_smartrecruiters_async(httpx_client):
    payload = load_ats_fixture("smartrecruiters.json")
    respx.get(url__regex=r"https://api\.smartrecruiters\.com/v1/companies/Acme/postings.*").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_smartrecruiters_async(
        httpx_client,
        "https://api.smartrecruiters.com/v1/companies/Acme/postings",
    )
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_scrape_workday_async(httpx_client):
    payload = load_ats_fixture("workday.json")
    ats_url = (
        "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|"
        "https://acme.wd3.myworkdayjobs.com/en-US/careers"
    )
    respx.post("https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_workday_async(httpx_client, ats_url)
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_scrape_bol_async(httpx_client):
    payload = load_ats_fixture("bol.json")
    respx.post("https://careers.bol.com/wp-json/wp/v2/hggns/multilanguage_vacature_search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = await sj.scrape_bol_async(httpx_client, "https://careers.bol.com/en/jobs/")
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_scrape_deel_async(httpx_client):
    html = load_ats_fixture("deel.html")
    respx.get("https://jobs.deel.com/acme").mock(return_value=httpx.Response(200, text=html))
    jobs = await sj.scrape_deel_async(httpx_client, "https://jobs.deel.com/acme")
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_detect_ats_static_async(httpx_client):
    html = "Visit https://jobs.lever.co/acme for openings"
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(200, text=html))
    ats_type, ats_url = await sj.detect_ats_static_async(httpx_client, "https://example.com/careers")
    assert ats_type == "lever"
    assert "acme" in ats_url


@respx.mock
async def test_scrape_join_async(httpx_client):
    next_data = load_ats_fixture("join_next_data.json")
    api_data = load_ats_fixture("join_api.json")
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>'
    respx.get("https://join.com/companies/acme-corp").mock(
        return_value=httpx.Response(200, text=html)
    )
    respx.get(url__regex=r"https://join\.com/api/public/companies/4242/jobs.*").mock(
        return_value=httpx.Response(200, json=api_data)
    )
    jobs = await sj.scrape_join_async(httpx_client, "https://join.com/companies/acme-corp")
    assert any("Golang" in j["title"] or "Backend" in j["title"] for j in jobs)


@respx.mock
async def test_scrape_generic_async(httpx_client):
    html = '<html><body><a href="/jobs/backend-dev">Backend Developer</a></body></html>'
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(200, text=html))
    jobs = await sj.scrape_generic_async(httpx_client, "https://example.com/careers")
    assert len(jobs) >= 1


@respx.mock
async def test_get_jobs_async_cached_greenhouse(httpx_client):
    payload = {
        "jobs": [
            {
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Berlin"},
            }
        ]
    }
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    company = {
        "name": "Acme",
        "careers_url": "https://boards.greenhouse.io/acme",
        "ats_type": "greenhouse",
        "ats_url": "https://boards.greenhouse.io/acme",
    }
    jobs = await sj.get_jobs_async(httpx_client, company, relevant_only=True)
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_fetch_job_description_async(httpx_client):
    html = "<html><body>" + ("word " * 100) + "visa sponsorship available</body></html>"
    respx.get("https://example.com/jobs/1").mock(return_value=httpx.Response(200, text=html))
    text = await sj.fetch_job_description_async(httpx_client, "https://example.com/jobs/1")
    assert "visa sponsorship" in text


@respx.mock
async def test_scrape_job_shop_async(httpx_client):
    page_html = load_ats_fixture("job_shop_page.html")
    search_payload = load_ats_fixture("job_shop.json")
    respx.get(url__regex=r"https://careers\.acme\.example\.com/.*").mock(
        return_value=httpx.Response(200, text=page_html)
    )
    respx.post("https://api.my-job-shop.com/api/typesense/multi_search").mock(
        return_value=httpx.Response(200, json=search_payload)
    )
    jobs = await sj.scrape_job_shop_async(
        httpx_client,
        "https://careers.acme.example.com/",
    )
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_get_jobs_async_auto_detect(httpx_client, monkeypatch):
    payload = {
        "jobs": [
            {
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Berlin"},
            }
        ]
    }
    respx.get("https://example.com/careers").mock(
        return_value=httpx.Response(200, text="https://boards.greenhouse.io/acme")
    )
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    monkeypatch.setattr(sj, "detect_ats_via_playwright", lambda *a, **k: (None, None))
    company = {"name": "DetectCo", "careers_url": "https://example.com/careers"}
    jobs = await sj.get_jobs_async(httpx_client, company, relevant_only=True)
    assert company["ats_type"] == "greenhouse"
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
@pytest.mark.parametrize(
    "ats_type,ats_url,setup",
    [
        (
            "workable",
            "https://apply.workable.com/acme/",
            lambda: respx.post("https://apply.workable.com/api/v2/accounts/acme/jobs").mock(
                return_value=httpx.Response(200, json=load_ats_fixture("workable.json"))
            ),
        ),
        (
            "recruitee",
            "https://acme.recruitee.com/",
            lambda: respx.get("https://acme.recruitee.com/api/offers/").mock(
                return_value=httpx.Response(200, json=load_ats_fixture("recruitee.json"))
            ),
        ),
        (
            "smartrecruiters",
            "https://api.smartrecruiters.com/v1/companies/Acme/postings",
            lambda: respx.get(url__regex=r"https://api\.smartrecruiters\.com/v1/companies/Acme/postings.*").mock(
                return_value=httpx.Response(200, json=load_ats_fixture("smartrecruiters.json"))
            ),
        ),
        (
            "workday",
            "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs|https://acme.wd3.myworkdayjobs.com/en-US/careers",
            lambda: respx.post(
                "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/careers/jobs"
            ).mock(return_value=httpx.Response(200, json=load_ats_fixture("workday.json"))),
        ),
        (
            "bol",
            "https://careers.bol.com/en/jobs/",
            lambda: respx.post(
                "https://careers.bol.com/wp-json/wp/v2/hggns/multilanguage_vacature_search"
            ).mock(return_value=httpx.Response(200, json=load_ats_fixture("bol.json"))),
        ),
    ],
)
async def test_get_jobs_async_ats_types(httpx_client, ats_type, ats_url, setup):
    setup()
    company = {
        "name": "Co",
        "careers_url": ats_url.split("|")[0] if ats_type == "workday" else ats_url,
        "ats_type": ats_type,
        "ats_url": ats_url,
    }
    jobs = await sj.get_jobs_async(httpx_client, company, relevant_only=True)
    assert len(jobs) >= 1


@respx.mock
async def test_get_jobs_async_generic_playwright_fallback(httpx_client, monkeypatch):
    html = '<html><body><a href="/jobs/backend-dev">Backend Developer</a></body></html>'
    respx.get("https://example.com/careers").mock(return_value=httpx.Response(200, text=html))
    monkeypatch.setattr(
        sj,
        "scrape_with_playwright",
        lambda url, **kw: [{"title": "Playwright Backend Engineer", "url": "https://example.com/j/1"}],
    )
    monkeypatch.setattr(sj, "PLAYWRIGHT_AVAILABLE", True)
    company = {"name": "Co", "careers_url": "https://example.com/careers", "ats_type": "generic", "ats_url": ""}
    jobs = await sj.get_jobs_async(httpx_client, company, relevant_only=True)
    assert any("Backend" in j["title"] for j in jobs)


@respx.mock
async def test_enrich_jobs_async_with_client(httpx_client):
    html = "<html><body>" + ("word " * 100) + "relocation package</body></html>"
    respx.get("https://example.com/jobs/1").mock(return_value=httpx.Response(200, text=html))
    jobs = [{"title": "Backend Engineer", "url": "https://example.com/jobs/1"}]
    company = {"ats_type": None}
    out = await sj.enrich_jobs_async_with_client(httpx_client, jobs, company)
    assert out[0]["visa_sponsorship"] is True

