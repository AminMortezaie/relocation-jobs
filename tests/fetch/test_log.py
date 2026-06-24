from __future__ import annotations

from relocation_jobs.fetch.log import bind_fetch_log_context, configure_fetch_logging, log_event, log_http_exchange


def test_fetch_log_event_includes_context(capsys):
    configure_fetch_logging()
    log_event(
        "single-company fetch worker started",
        run_id=12,
        country="uk",
        company="Acme Backend Ltd",
        scope="company",
    )
    err = capsys.readouterr().err
    assert "run=12" in err
    assert "country=uk" in err
    assert 'company="Acme Backend Ltd"' in err
    assert "single-company fetch worker started" in err


def test_fetch_http_exchange_logs_job_url_and_bodies(capsys):
    configure_fetch_logging()
    bind_fetch_log_context(run_id=7, company="Acme", scope="company", country="uk")
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
    err = capsys.readouterr().err
    assert "run=7" in err
    assert "position_url=https://boards.greenhouse.io/acme/jobs/42" in err
    assert 'position="Backend Engineer"' in err
    assert "request_url=https://boards-api.greenhouse.io/v1/boards/acme/jobs/42" in err
    assert "status=200" in err
    assert "response_body=" in err
    assert "Visa sponsorship" in err
