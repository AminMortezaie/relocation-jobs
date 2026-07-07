from __future__ import annotations

from relocation_jobs.scrape.dom_listing import jobs_from_listing_html


def test_jobs_from_listing_html_extracts_job_links():
    html = """
    <html><body>
      <a href="jobs/backend-engineer">Backend Engineer</a>
      <a href="/jobs/show_more">Show 10 more</a>
      <a href="/about">About us</a>
    </body></html>
    """
    jobs = jobs_from_listing_html(
        html,
        "https://jobs.ashbyhq.com/acme/",
        relevant_only=False,
    )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Backend Engineer"
    assert jobs[0]["url"] == "https://jobs.ashbyhq.com/acme/jobs/backend-engineer"


def test_jobs_from_listing_html_extracts_careers_slug_links():
    html = """
    <html><body>
      <a href="/careers/technical-writer/">Technical Writer</a>
      <a href="/careers/">Careers home</a>
      <a href="/careers/#careers-list">View Careers</a>
    </body></html>
    """
    jobs = jobs_from_listing_html(
        html,
        "https://www.brightpattern.com/careers/#careers-list",
        relevant_only=False,
    )
    assert len(jobs) == 1
    assert "Technical Writer" in jobs[0]["title"]
    assert jobs[0]["url"] == "https://www.brightpattern.com/careers/technical-writer/"
