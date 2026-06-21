"""Per-user job and company tracking in SQLite."""

import pytest

from relocation_jobs.db import (
    load_company_tracking,
    load_job_tracking,
    set_company_applied_db,
    set_job_applied_db,
    set_job_not_for_me_db,
    set_job_rejected_db,
)


@pytest.mark.integration
def test_job_applied_tracking(test_user, seeded_catalog):
    uid = test_user["id"]
    url = "https://boards.greenhouse.io/acmebackend/jobs/123456?gh_jid=123456"

    set_job_applied_db(uid, "uk", "Acme Backend Ltd", url, True, job_title="Senior Backend Engineer")
    tracking = load_job_tracking(uid)
    key = ("uk", "Acme Backend Ltd", url)
    assert key in tracking
    assert bool(tracking[key]["applied"]) is True
    assert tracking[key]["applied_date"]

    set_job_applied_db(uid, "uk", "Acme Backend Ltd", url, False, job_title="Senior Backend Engineer")
    tracking = load_job_tracking(uid)
    assert bool(tracking[key]["applied"]) is False


@pytest.mark.integration
def test_job_rejected_and_not_for_me(test_user):
    uid = test_user["id"]
    url = "https://example.com/job/1"

    set_job_rejected_db(uid, "uk", "Acme", url, True, job_title="Engineer")
    set_job_not_for_me_db(uid, "uk", "Acme", url, not_for_me=True)

    tracking = load_job_tracking(uid)
    row = tracking[("uk", "Acme", url)]
    assert bool(row["rejected"]) is True
    assert bool(row["not_for_me"]) is True


@pytest.mark.integration
def test_company_applied_tracking(test_user):
    uid = test_user["id"]
    set_company_applied_db(uid, "uk", "Acme Backend Ltd", True)
    company_tracking = load_company_tracking(uid)
    assert bool(company_tracking[("uk", "Acme Backend Ltd")]["company_applied"]) is True
