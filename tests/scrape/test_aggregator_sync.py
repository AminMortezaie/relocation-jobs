from __future__ import annotations

from relocation_jobs.scrape.aggregator_sync import (
    group_jobs_by_employer,
    is_aggregator_ats,
    should_skip_country_fetch,
)


def test_aggregator_ats_helpers():
    assert is_aggregator_ats("remoteok")
    assert is_aggregator_ats("remotedxb")
    assert is_aggregator_ats("joblet")
    assert not is_aggregator_ats("greenhouse")
    assert should_skip_country_fetch("sourced")
    assert not should_skip_country_fetch("remoteok")
    assert not should_skip_country_fetch("joblet")


def test_group_jobs_by_employer():
    grouped = group_jobs_by_employer(
        [
            {
                "title": "Backend Engineer",
                "url": "https://example.com/a",
                "employer": "Acme",
                "description_text": "APIs",
            },
            {
                "title": "Platform Engineer",
                "url": "https://example.com/b",
                "employer": "Acme",
            },
            {
                "title": "Missing employer",
                "url": "https://example.com/c",
            },
            {
                "title": "Other",
                "url": "https://example.com/d",
                "employer": "Orbit",
            },
        ]
    )
    assert set(grouped) == {"Acme", "Orbit"}
    assert len(grouped["Acme"]) == 2
    assert grouped["Acme"][0]["description_text"] == "APIs"
    assert "employer" not in grouped["Acme"][0]
