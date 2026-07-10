from __future__ import annotations

import logging

from relocation_jobs.fetch.log import bind_fetch_log_context, configure_fetch_logging, log_event, log_http_exchange


def test_fetch_log_event_includes_context(caplog):
    configure_fetch_logging()
    with caplog.at_level(logging.INFO, logger="relocation_jobs.fetch"):
        log_event(
            "single-company fetch worker started",
            run_id=12,
            country="uk",
            company="Acme Backend Ltd",
            scope="company",
        )
    text = caplog.text
    assert "run=12" in text
    assert "country=uk" in text
    assert 'company="Acme Backend Ltd"' in text
    assert "single-company fetch worker started" in text


def test_fetch_http_exchange_logs_job_url_and_bodies(caplog):
    configure_fetch_logging()
    bind_fetch_log_context(run_id=7, company="Acme", scope="company", country="uk")
    with caplog.at_level(logging.INFO, logger="relocation_jobs.fetch"):
        log_http_exchange(
            kind="job",
            method="GET",
            url="https://boards-api.greenhouse.io/v1/boards/acme/jobs/42",
            job_url="https://boards.greenhouse.io/acme/jobs/42",
            job_title="Backend Engineer",
            response_status=200,
            response_body='{"content":"<p>Visa sponsorship available</p>"}',
            response_bytes=48,
        )
    text = caplog.text
    assert "run=7" in text
    assert "position_url=https://boards.greenhouse.io/acme/jobs/42" in text
    assert 'position="Backend Engineer"' in text
    assert "request_url=https://boards-api.greenhouse.io/v1/boards/acme/jobs/42" in text
    assert "status=200" in text
    assert "response_body=" in text
    assert "Visa sponsorship" in text
