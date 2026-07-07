from __future__ import annotations

from relocation_jobs.scrape.boards.workday import workday_job_detail_api_url
from relocation_jobs.scrape.job_text import fetch_workday_job_detail

_CRITEO_JOB = (
    "https://criteo.wd3.myworkdayjobs.com/en-US/Criteo_Career_Site/job/Paris/"
    "Site-Reliability-Engineer---Platform-PRE_r19497"
)


def test_workday_job_detail_api_url_criteo():
    assert workday_job_detail_api_url(_CRITEO_JOB) == (
        "https://criteo.wd3.myworkdayjobs.com/wday/cxs/criteo/"
        "Criteo_Career_Site/job/Site-Reliability-Engineer---Platform-PRE_r19497"
    )


def test_workday_job_detail_api_url_myworkdaysite():
    url = (
        "https://wd3.myworkdaysite.com/en-US/takeaway/JET-ECS-R/job/"
        "Amsterdam/Some-Job-Title_r12345"
    )
    assert workday_job_detail_api_url(url) == (
        "https://wd3.myworkdaysite.com/wday/cxs/takeaway/"
        "JET-ECS-R/job/Some-Job-Title_r12345"
    )


def test_fetch_workday_job_detail_criteo():
    result = fetch_workday_job_detail(_CRITEO_JOB)
    assert "Site Reliability Engineer" in result.text
    assert result.location == "Paris"
