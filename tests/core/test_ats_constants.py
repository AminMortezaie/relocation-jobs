from __future__ import annotations

from relocation_jobs.companies.service import detect_ats_for_company
from relocation_jobs.scrape.ats_resolve import apply_known_ats_override


def test_wolt_known_ats_overrides_recruitee_careers_host_guess():
    ats_type, ats_url = detect_ats_for_company("Wolt", "https://careers.wolt.com/")
    assert ats_type == "greenhouse"
    assert ats_url == "https://boards.greenhouse.io/wolt"


def test_apply_known_ats_override_fixes_cached_recruitee_for_wolt():
    company = {
        "name": "Wolt",
        "careers_url": "https://careers.wolt.com/",
        "ats_type": "recruitee",
        "ats_url": "https://wolt.recruitee.com/",
    }
    apply_known_ats_override(company)
    assert company["ats_type"] == "greenhouse"
    assert company["ats_url"] == "https://boards.greenhouse.io/wolt"
