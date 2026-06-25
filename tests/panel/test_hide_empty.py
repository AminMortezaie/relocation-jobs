from __future__ import annotations

import json

import pytest

from relocation_jobs.panel.flatten import _skip_company_after_jobs
from relocation_jobs.panel.service import flatten_companies_page
from relocation_jobs.panel.types import FlattenFilters
from relocation_jobs.positions.types import PositionFilters


def test_hide_empty_skips_not_for_me_only():
    filters = FlattenFilters(hide_empty=True)
    assert _skip_company_after_jobs(
        filters=filters,
        jobs=[],
        not_for_me_jobs=[{"url": "https://example.com/jobs/1"}],
        rejected_jobs=[],
        header={"company_applied": False},
    ) is True


def test_hide_empty_skips_rejected_only():
    filters = FlattenFilters(hide_empty=True)
    assert _skip_company_after_jobs(
        filters=filters,
        jobs=[],
        not_for_me_jobs=[],
        rejected_jobs=[{"url": "https://example.com/jobs/1"}],
        header={"company_applied": False},
    ) is True


def test_hide_empty_keeps_open_jobs():
    filters = FlattenFilters(hide_empty=True)
    assert _skip_company_after_jobs(
        filters=filters,
        jobs=[{"url": "https://example.com/jobs/1"}],
        not_for_me_jobs=[],
        rejected_jobs=[],
        header={"company_applied": False},
    ) is False


def test_hide_empty_keeps_rejected_only_when_rejections_filter_active():
    filters = FlattenFilters(
        hide_empty=True,
        position_filters=PositionFilters(rejected_only=True),
    )
    assert _skip_company_after_jobs(
        filters=filters,
        jobs=[],
        not_for_me_jobs=[],
        rejected_jobs=[{"url": "https://example.com/jobs/1"}],
        header={"company_applied": False},
    ) is False


@pytest.mark.fresh_db
def test_board_hide_empty_filters_not_for_me_only_company(v2_auth_client, db):
    from pathlib import Path

    from tests.helpers.seed import replace_matching_jobs, seed_country

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "country_uk_minimal.json"
    seed_country("uk", fixture)

    replace_matching_jobs("uk", "Acme Backend Ltd", [
        {"title": "Hidden role", "url": "https://boards.greenhouse.io/acmebackend/jobs/999"},
    ])
    v2_auth_client.post(
        "/api/jobs/not-for-me",
        json={
            "country": "uk",
            "company": "Acme Backend Ltd",
            "url": "https://boards.greenhouse.io/acmebackend/jobs/999",
            "reason": "not_for_me",
        },
    )

    unfiltered = v2_auth_client.get("/api/board?country=uk").get_json()
    assert len(unfiltered["companies"]) == 1

    filtered = v2_auth_client.get("/api/board?country=uk&hide_empty=1").get_json()
    assert filtered["companies"] == []
    assert filtered["meta"]["total_companies"] == 0


@pytest.mark.fresh_db
def test_flatten_companies_page_has_more_uses_filtered_stream(db, tmp_path):
    from tests.helpers.seed import seed_country

    data = {
        "source": "test",
        "companies": [
            {"name": "Alpha Co", "matching_jobs": [{"title": "Eng", "url": "https://example.com/alpha"}]},
            {"name": "Bravo Empty", "matching_jobs": []},
            {"name": "Charlie Co", "matching_jobs": [{"title": "Eng", "url": "https://example.com/charlie"}]},
        ],
    }
    path = tmp_path / "hide_empty_page.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    seed_country("uk", path)
    filters = FlattenFilters(country_key="uk", hide_empty=True)
    page_one, _, _, total, has_more = flatten_companies_page(
        filters,
        visible_offset=0,
        limit=1,
        count_total=True,
    )
    assert [row["name"] for row in page_one] == ["Alpha Co"]
    assert total == 2
    assert has_more is True

    page_two, _, _, _, has_more_page_two = flatten_companies_page(
        filters,
        visible_offset=1,
        limit=1,
        count_total=False,
    )
    assert [row["name"] for row in page_two] == ["Charlie Co"]
    assert has_more_page_two is False
