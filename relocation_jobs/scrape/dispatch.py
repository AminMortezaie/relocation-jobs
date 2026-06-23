"""ATS detection cache helpers and scraper dispatch."""

from __future__ import annotations

import asyncio

from relocation_jobs.core.ats_constants import (
    FORCE_KNOWN_ATS,
    HTTPX_AVAILABLE,
    KNOWN_ATS,
)
from relocation_jobs.core.ats_detection import (
    HEADERS,
    _detect_applytojob_from_url,
    _detect_bamboohr_from_url,
    _detect_deel_from_url,
    _detect_join_from_url,
    _detect_job_shop_from_url,
    _detect_recruitee_from_careers_host,
    _detect_smartrecruiters_from_careers_url,
    _detect_smartrecruiters_from_redcare_careers,
    _smartrecruiters_company_id,
)
from relocation_jobs.core.scrape_cancel import raise_if_cancelled
from relocation_jobs.scrape import http as _scrape_http
from relocation_jobs.scrape.ipc import report_activity
from relocation_jobs.scrape.listing import filter_relevant_jobs
from relocation_jobs.scrape.shim_bind import scrape_jobs_shim

if HTTPX_AVAILABLE:
    httpx = _scrape_http.httpx


def _scrapers():
    return scrape_jobs_shim()


def apply_known_ats_override(company: dict, save_fn=None) -> None:
    """Use KNOWN_ATS or join.com URL when cache is empty or wrongly set to generic."""
    name = company.get("name", "")
    cached = (company.get("ats_type") or "").strip()
    careers_url = company.get("careers_url") or ""

    if name in KNOWN_ATS:
        if not cached or cached == "generic" or name in FORCE_KNOWN_ATS:
            known_type, known_url = KNOWN_ATS[name]
            company["ats_type"] = known_type
            company["ats_url"] = known_url
            print(f"    Known override: {known_type} → {known_url}")
            if save_fn:
                save_fn()
        return

    sr = _detect_smartrecruiters_from_careers_url(careers_url)
    if sr[0]:
        cached_id = _smartrecruiters_company_id(company.get("ats_url") or "")
        expected_id = _smartrecruiters_company_id(sr[1])
        if cached != "smartrecruiters" or cached_id != expected_id:
            company["ats_type"] = sr[0]
            company["ats_url"] = sr[1]
            print(f"    SmartRecruiters careers URL: {sr[1]}")
            if save_fn:
                save_fn()
            return

    if careers_url and (not cached or cached == "generic"):
        detectors = (
            ("SmartRecruiters", _detect_smartrecruiters_from_careers_url),
            ("JobShop", _detect_job_shop_from_url),
            ("Deel", _detect_deel_from_url),
            ("Join", _detect_join_from_url),
            ("ApplyToJob", _detect_applytojob_from_url),
            ("BambooHR", _detect_bamboohr_from_url),
            ("Recruitee", _detect_recruitee_from_careers_host),
            ("SmartRecruiters", _detect_smartrecruiters_from_redcare_careers),
        )
        for label, detector in detectors:
            ats_type, ats_url = detector(careers_url)
            if ats_type:
                company["ats_type"] = ats_type
                company["ats_url"] = ats_url
                print(f"    {label} careers URL: {ats_url}")
                if save_fn:
                    save_fn()
                break


def effective_cached_ats(company: dict) -> tuple[str | None, str]:
    """Treat persisted ``generic`` as unknown — it is wrong too often."""
    cached = (company.get("ats_type") or "").strip()
    if cached == "generic":
        return None, ""
    if cached:
        return cached, company.get("ats_url") or ""
    return None, ""


def persist_detected_ats(
    company: dict,
    ats_type: str | None,
    ats_url: str,
    save_fn=None,
) -> str:
    """Persist a concrete ATS type; use generic scraper at runtime only when unknown."""
    if ats_type:
        company["ats_type"] = ats_type
        company["ats_url"] = ats_url or ""
    else:
        company["ats_type"] = ""
        company["ats_url"] = ""
    if save_fn:
        save_fn()
    return ats_type or "generic"


def get_jobs(company: dict, save_fn=None) -> list[dict]:
    """
    Detect or use cached ATS, scrape jobs, and return list.
    If save_fn is provided it's called after ATS detection to persist cache.
    """
    sj = _scrapers()
    name = company["name"]
    careers_url = company.get("careers_url")
    if not careers_url:
        return []

    apply_known_ats_override(company, save_fn)

    ats_type, ats_url = effective_cached_ats(company)

    if not ats_type:
        if name in KNOWN_ATS:
            ats_type, ats_url = KNOWN_ATS[name]
            print(f"    Known: {ats_type} → {ats_url}")
        else:
            ats_type, ats_url = sj.detect_ats_static(careers_url)

            if not ats_type:
                print(f"    Detecting ATS via Playwright...")
                ats_type, ats_url = sj.detect_ats_via_playwright(careers_url)

            if ats_type:
                print(f"    Detected: {ats_type} → {ats_url}")
            else:
                print(f"    No ATS detected, using generic Playwright scraper")

        if ats_type and ats_url:
            slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
            is_proxy = "careers-analytics" in ats_url
            is_bad_slug = slug in ("embed", "jobs", "")
            if (is_bad_slug or is_proxy) and name in KNOWN_ATS:
                print(f"    Bad detection (slug='{slug}'), using known correction")
                ats_type, ats_url = KNOWN_ATS[name]

        ats_type = persist_detected_ats(company, ats_type, ats_url, save_fn)
        ats_url = company.get("ats_url") or ats_url

    effective_url = ats_url or careers_url

    if ats_type == "personio":
        return sj.scrape_personio(effective_url)
    if ats_type in ("lever", "lever_eu"):
        return sj.scrape_lever(effective_url)
    if ats_type in ("greenhouse", "greenhouse_eu"):
        return sj.scrape_greenhouse(effective_url)
    if ats_type == "bol":
        return sj.scrape_bol(careers_url)
    if ats_type == "job_shop":
        return sj.scrape_job_shop(effective_url or careers_url)
    if ats_type == "ashby":
        return sj.scrape_ashby(effective_url)
    if ats_type == "workable":
        return sj.scrape_workable(effective_url)
    if ats_type == "recruitee":
        return sj.scrape_recruitee(effective_url)
    if ats_type == "smartrecruiters":
        return sj.scrape_smartrecruiters(effective_url)
    if ats_type == "teamtailor":
        return sj.scrape_teamtailor(effective_url, careers_url)
    if ats_type == "join":
        return sj.scrape_join(effective_url or careers_url)
    if ats_type == "deel":
        return sj.scrape_deel(effective_url or careers_url)
    if ats_type == "applytojob":
        return sj.scrape_applytojob(effective_url or careers_url)
    if ats_type == "bamboohr":
        return sj.scrape_bamboohr(effective_url or careers_url)
    if ats_type == "movingimage":
        return sj.scrape_movingimage(effective_url or careers_url)
    if ats_type == "project_a":
        return sj.scrape_project_a(effective_url or careers_url)
    if ats_type == "workday":
        return sj.scrape_workday(effective_url)
    if ats_type == "hirehive":
        return sj.scrape_hirehive(effective_url)
    if ats_type == "epam":
        return sj.scrape_epam(effective_url)
    if ats_type == "rss":
        return sj.scrape_rss(effective_url)
    if ats_type == "jibe":
        return sj.scrape_jibe(effective_url or careers_url)
    if ats_type == "atlassian":
        return sj.scrape_atlassian(effective_url or careers_url)

    jobs = sj.scrape_generic(careers_url)
    if not jobs and sj.PLAYWRIGHT_AVAILABLE:
        jobs = sj.scrape_with_playwright(careers_url)
    return jobs


async def get_jobs_async(
    client: httpx.AsyncClient,
    company: dict,
    save_fn=None,
    *,
    relevant_only: bool = True,
) -> list[dict]:
    sj = _scrapers()
    raise_if_cancelled()
    name = company["name"]
    careers_url = company.get("careers_url")
    if not careers_url:
        return []

    apply_known_ats_override(company, save_fn)

    ats_type, ats_url = effective_cached_ats(company)

    if not ats_type:
        if name in KNOWN_ATS:
            ats_type, ats_url = KNOWN_ATS[name]
            print(f"    Known: {ats_type} → {ats_url}")
        else:
            ats_type, ats_url = await sj.detect_ats_static_async(client, careers_url)
            if not ats_type:
                raise_if_cancelled()
                print(f"    Detecting ATS via Playwright...")
                ats_type, ats_url = await asyncio.to_thread(
                    sj.detect_ats_via_playwright, careers_url
                )
            if ats_type:
                print(f"    Detected: {ats_type} → {ats_url}")
            else:
                print(f"    No ATS detected, using generic Playwright scraper")

        if ats_type and ats_url:
            slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
            is_proxy = "careers-analytics" in ats_url
            is_bad_slug = slug in ("embed", "jobs", "")
            if (is_bad_slug or is_proxy) and name in KNOWN_ATS:
                print(f"    Bad detection (slug='{slug}'), using known correction")
                ats_type, ats_url = KNOWN_ATS[name]

        ats_type = persist_detected_ats(company, ats_type, ats_url, save_fn)
        ats_url = company.get("ats_url") or ats_url

    effective_url = ats_url or careers_url
    raise_if_cancelled()

    runtime_ats = ats_type or "generic"
    report_activity(
        f"Fetching roles via {runtime_ats}",
        detail=effective_url if effective_url != careers_url else careers_url,
    )

    if ats_type == "personio":
        jobs = await sj.scrape_personio_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type in ("lever", "lever_eu"):
        jobs = await sj.scrape_lever_async(client, effective_url)
    elif ats_type == "greenhouse_eu":
        jobs = await sj.scrape_greenhouse_async(client, effective_url, eu=True)
    elif ats_type == "greenhouse":
        jobs = await sj.scrape_greenhouse_async(client, effective_url, eu=False)
    elif ats_type == "bol":
        jobs = await sj.scrape_bol_async(client, careers_url)
    elif ats_type == "job_shop":
        jobs = await sj.scrape_job_shop_async(
            client, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "ashby":
        jobs = await sj.scrape_ashby_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "workable":
        jobs = await sj.scrape_workable_async(client, effective_url)
    elif ats_type == "recruitee":
        jobs = await sj.scrape_recruitee_async(client, effective_url)
    elif ats_type == "smartrecruiters":
        jobs = await sj.scrape_smartrecruiters_async(
            client, effective_url, relevant_only=relevant_only
        )
    elif ats_type == "teamtailor":
        jobs = await asyncio.to_thread(
            sj.scrape_teamtailor, effective_url, careers_url, relevant_only=relevant_only
        )
    elif ats_type == "join":
        jobs = await sj.scrape_join_async(
            client, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "deel":
        jobs = await sj.scrape_deel_async(
            client, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "applytojob":
        jobs = await asyncio.to_thread(
            sj.scrape_applytojob, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "bamboohr":
        jobs = await asyncio.to_thread(
            sj.scrape_bamboohr, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "movingimage":
        jobs = await asyncio.to_thread(
            sj.scrape_movingimage, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "project_a":
        jobs = await asyncio.to_thread(
            sj.scrape_project_a, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "workday":
        jobs = await sj.scrape_workday_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "hirehive":
        jobs = await sj.scrape_hirehive_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "epam":
        jobs = await sj.scrape_epam_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "rss":
        jobs = await sj.scrape_rss_async(client, effective_url, relevant_only=relevant_only)
    elif ats_type == "jibe":
        jobs = await asyncio.to_thread(
            sj.scrape_jibe, effective_url or careers_url, relevant_only=relevant_only
        )
    elif ats_type == "atlassian":
        jobs = await asyncio.to_thread(
            sj.scrape_atlassian, effective_url or careers_url, relevant_only=relevant_only
        )
    else:
        jobs = await sj.scrape_generic_async(client, careers_url, relevant_only=relevant_only)
        if not jobs and sj.PLAYWRIGHT_AVAILABLE:
            raise_if_cancelled()
            jobs = await asyncio.to_thread(
                sj.scrape_with_playwright, careers_url, relevant_only=relevant_only
            )

    raise_if_cancelled()
    jobs = filter_relevant_jobs(jobs, relevant_only)
    if relevant_only:
        report_activity(f"Loaded {len(jobs)} matching role(s)")
    else:
        report_activity(f"Loaded {len(jobs)} role(s) from careers page")
    return jobs
