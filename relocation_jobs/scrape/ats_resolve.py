from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Optional

from relocation_jobs.companies.service import detect_ats_for_company
from relocation_jobs.core.ats_constants import FORCE_KNOWN_ATS, KNOWN_ATS
from relocation_jobs.core.ats_detection import (
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

PersistBoard = Optional[Callable[[], None]]


def effective_cached_ats(company: dict) -> tuple[str | None, str]:
    cached = (company.get("ats_type") or "").strip()
    if cached == "generic":
        return None, ""
    if cached:
        return cached, company.get("ats_url") or ""
    return None, ""


def _finalize_detected_ats(name: str, ats_type: str | None, ats_url: str) -> tuple[str, str]:
    if not ats_type or not ats_url:
        return ats_type or "", ats_url or ""
    slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
    is_proxy = "careers-analytics" in ats_url
    is_bad_slug = slug in ("embed", "jobs", "")
    if (is_bad_slug or is_proxy) and name in KNOWN_ATS:
        return KNOWN_ATS[name]
    return ats_type, ats_url


def apply_known_ats_override(company: dict, persist_board: PersistBoard = None) -> None:
    name = company.get("name", "")
    cached = (company.get("ats_type") or "").strip()
    careers_url = company.get("careers_url") or ""

    if name in KNOWN_ATS:
        if not cached or cached == "generic" or name in FORCE_KNOWN_ATS:
            known_type, known_url = KNOWN_ATS[name]
            company["ats_type"] = known_type
            company["ats_url"] = known_url
            if persist_board:
                persist_board()
        return

    smartrecruiters = _detect_smartrecruiters_from_careers_url(careers_url)
    if smartrecruiters[0]:
        cached_id = _smartrecruiters_company_id(company.get("ats_url") or "")
        expected_id = _smartrecruiters_company_id(smartrecruiters[1])
        if cached != "smartrecruiters" or cached_id != expected_id:
            company["ats_type"] = smartrecruiters[0]
            company["ats_url"] = smartrecruiters[1]
            if persist_board:
                persist_board()
            return

    if careers_url and (not cached or cached == "generic"):
        detectors = (
            _detect_smartrecruiters_from_careers_url,
            _detect_job_shop_from_url,
            _detect_deel_from_url,
            _detect_join_from_url,
            _detect_applytojob_from_url,
            _detect_bamboohr_from_url,
            _detect_recruitee_from_careers_host,
            _detect_smartrecruiters_from_redcare_careers,
        )
        for detector in detectors:
            ats_type, ats_url = detector(careers_url)
            if ats_type:
                company["ats_type"] = ats_type
                company["ats_url"] = ats_url
                if persist_board:
                    persist_board()
                break


def persist_detected_ats(
    company: dict,
    ats_type: str | None,
    ats_url: str,
    persist_board: PersistBoard = None,
) -> str:
    if ats_type:
        company["ats_type"] = ats_type
        company["ats_url"] = ats_url or ""
    else:
        company["ats_type"] = ""
        company["ats_url"] = ""
    if persist_board:
        persist_board()
    return ats_type or "generic"


async def ensure_company_ats(
    client,
    company: dict,
    *,
    persist_board: PersistBoard = None,
) -> None:
    del client
    cached = (company.get("ats_type") or "").strip().lower()
    if cached == "generic":
        return

    apply_known_ats_override(company, persist_board)
    ats_type, ats_url = effective_cached_ats(company)
    if ats_type:
        return

    careers_url = (company.get("careers_url") or "").strip()
    if not careers_url:
        return

    name = company.get("name") or ""
    if name in KNOWN_ATS:
        ats_type, ats_url = KNOWN_ATS[name]
    else:
        ats_type, ats_url = await asyncio.to_thread(
            detect_ats_for_company,
            name,
            careers_url,
        )

    ats_type, ats_url = _finalize_detected_ats(name, ats_type or None, ats_url or "")
    if not ats_type:
        ats_type = "generic"
    persist_detected_ats(company, ats_type, ats_url or "", persist_board)
