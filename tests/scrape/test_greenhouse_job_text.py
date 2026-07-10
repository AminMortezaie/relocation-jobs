from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.http_mock import MockResponse

from relocation_jobs.scrape.boards.greenhouse import (
    greenhouse_job_content,
    greenhouse_job_ids_from_url,
)
from relocation_jobs.scrape.descriptions import (
    format_job_description,
    needs_getyourguide_refetch,
)
from relocation_jobs.scrape.job_text import fetch_greenhouse_job_text

_JOB_URL = "https://www.getyourguide.careers/jobs/8007209"
_API_URL = "https://boards-api.greenhouse.io/v1/boards/getyourguide/jobs/8007209"
_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "ats"
    / "greenhouse_job_detail.json"
)


def test_greenhouse_job_ids_from_url_getyourguide():
    assert greenhouse_job_ids_from_url(_JOB_URL) == ("getyourguide", "8007209")


def test_greenhouse_job_ids_from_url_gh_jid_with_board_slug():
    url = "https://careers.hellofresh.com/global/en/job/7864482?gh_jid=7864482"
    assert greenhouse_job_ids_from_url(url) is None
    assert greenhouse_job_ids_from_url(url, board_slug="hellofresh") == (
        "hellofresh",
        "7864482",
    )


def test_greenhouse_job_ids_from_branded_workato_gh_jid():
    url = "https://www.workato.com/careers?gh_jid=8499680002#open-roles"
    assert greenhouse_job_ids_from_url(url) == ("workato", "8499680002")


def test_fetch_greenhouse_job_text_getyourguide(monkeypatch):
    payload = json.loads(_FIXTURE.read_text())

    def fake_get(url, *args, **kwargs):
        assert url == _API_URL
        return MockResponse(json_data=payload)

    monkeypatch.setattr("relocation_jobs.scrape.boards.greenhouse.requests.get", fake_get)
    result = __import__(
        "relocation_jobs.scrape.job_text",
        fromlist=["fetch_greenhouse_job_detail"],
    ).fetch_greenhouse_job_detail(_JOB_URL)
    assert "<h3>" in result.text
    assert "Change the way the world travels" in result.text
    assert result.location == "Berlin, Germany"


def test_greenhouse_job_content_unescapes_entities(monkeypatch):
    payload = {"content": "&lt;p&gt;Hello &amp; welcome&lt;/p&gt;"}

    def fake_get(url, *args, **kwargs):
        return MockResponse(json_data=payload)

    monkeypatch.setattr("relocation_jobs.scrape.boards.greenhouse.requests.get", fake_get)
    assert greenhouse_job_content("getyourguide", "123") == "<p>Hello & welcome</p>"


def test_needs_getyourguide_refetch_detects_page_scrape():
    noisy = (
        "senior software engineer | jobs at getyourguide life at getyourguide "
        "guiding principles our teams tech at getyourguide how we hire open roles"
    )
    assert needs_getyourguide_refetch(noisy) is True
    assert needs_getyourguide_refetch("<h3><strong>Role</strong></h3><p>Build APIs.</p>") is False
