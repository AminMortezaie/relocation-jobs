from __future__ import annotations

from relocation_jobs.v2.fetch.repo import insert_attempt, list_attempts, update_attempt
from relocation_jobs.v2.fetch.types import AttemptStatus

FIXTURE_COMPANY = "Acme Backend Ltd"
FIXTURE_CAREERS_URL = "https://boards.greenhouse.io/acmebackend"


def test_insert_and_update_attempt_lifecycle(db):
    attempt_id = insert_attempt(
        country="uk",
        company_name=FIXTURE_COMPANY,
        careers_url=FIXTURE_CAREERS_URL,
        ats_type="greenhouse",
        fetch_run_id=None,
    )
    assert attempt_id > 0

    update_attempt(
        attempt_id,
        status=AttemptStatus.OK,
        jobs_total=12,
        jobs_new=3,
        message=f"[1/1] {FIXTURE_COMPANY} — 12 matching job(s)",
    )

    rows = list_attempts(country="uk", company_name=FIXTURE_COMPANY)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == AttemptStatus.OK
    assert row.jobs_total == 12
    assert row.jobs_new == 3
    assert row.careers_url == FIXTURE_CAREERS_URL
    assert row.finished_at
    assert row.duration_seconds is not None


def test_list_attempts_filters_by_status(db):
    ok_id = insert_attempt(country="uk", company_name=FIXTURE_COMPANY)
    update_attempt(ok_id, status=AttemptStatus.OK, jobs_total=1)

    err_id = insert_attempt(country="uk", company_name="Broken Co")
    update_attempt(
        err_id,
        status=AttemptStatus.ERROR,
        error_message="timeout",
        message="[1/89] Broken Co — Error: timeout",
    )

    errors = list_attempts(country="uk", status=AttemptStatus.ERROR)
    assert len(errors) == 1
    assert errors[0].company_name == "Broken Co"
    assert errors[0].error_message == "timeout"
