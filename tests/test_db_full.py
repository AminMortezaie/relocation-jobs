"""Full coverage for relocation_jobs.db tracking and user helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from relocation_jobs.db import (
    clear_company_tracking,
    count_jobs_applied_db,
    count_jobs_applied_today_db,
    create_user,
    get_user_by_id,
    get_user_by_username,
    init_db,
    load_company_tracking,
    load_job_status_history,
    load_job_tracking,
    migrate_tracking_from_json,
    reapply_job_db,
    rename_company_tracking,
    rename_user,
    set_company_applied_db,
    set_company_awaiting_response_db,
    set_job_applied_db,
    set_job_ats_score_db,
    set_job_looking_to_apply_db,
    set_job_rejected_db,
    set_job_seen_db,
    set_job_waiting_referral_db,
    sync_company_applied_from_jobs_db,
    tracking_is_empty,
    update_user_password,
    user_count,
)
from relocation_jobs.core.job_identity import normalize_job_url


@pytest.mark.integration
def test_create_user_validation_and_lookup(db):
    with pytest.raises(ValueError, match="Username is required"):
        create_user("  ", generate_password_hash("pass12345"))

    user = create_user("LookupUser", generate_password_hash("pass12345"))
    assert user["username"] == "LookupUser"
    assert get_user_by_username("lookupuser")["id"] == user["id"]
    assert get_user_by_id(user["id"])["username"] == "LookupUser"
    assert get_user_by_id(99999) is None
    assert user_count() >= 1


@pytest.mark.integration
def test_update_password_and_rename_user(test_user):
    uid = test_user["id"]
    new_hash = generate_password_hash("newpass12345")
    assert update_user_password("testuser", new_hash) is True
    row = get_user_by_username("testuser")
    assert check_password_hash(row["password_hash"], "newpass12345")

    assert rename_user(uid, "renamed_user") is True
    assert get_user_by_username("renamed_user")["id"] == uid
    assert update_user_password("nobody", new_hash) is False


@pytest.mark.integration
def test_looking_to_apply_and_reapply(test_user):
    uid = test_user["id"]
    url = "https://example.com/jobs/1"

    result = set_job_looking_to_apply_db(
        uid, "uk", "Acme", url, True, job_title="Engineer"
    )
    assert result["looking_to_apply"] is True
    assert result["looking_to_apply_date"]

    tracking = load_job_tracking(uid)
    assert bool(tracking[("uk", "Acme", url)]["looking_to_apply"]) is True

    set_job_rejected_db(uid, "uk", "Acme", url, True)
    reapply = reapply_job_db(uid, "uk", "Acme", url)
    assert reapply["rejected"] is False

    set_job_looking_to_apply_db(uid, "uk", "Acme", url, False)
    tracking = load_job_tracking(uid)
    assert bool(tracking[("uk", "Acme", url)]["looking_to_apply"]) is False


@pytest.mark.integration
def test_seen_tracking_with_url_aliases(test_user):
    uid = test_user["id"]
    stored = "https://boards.greenhouse.io/acme/jobs/1?gh_jid=1"
    alias = "https://www.boards.greenhouse.io/acme/jobs/1?gh_jid=1&utm=foo"

    set_job_seen_db(uid, "uk", "Acme", stored, True, job_title="Role")
    seen = set_job_seen_db(uid, "uk", "Acme", alias, True)
    assert seen["seen"] is True
    assert seen["seen_date"]

    cleared = set_job_seen_db(uid, "uk", "Acme", alias, False)
    assert cleared["seen"] is False
    assert cleared["seen_date"] == ""


@pytest.mark.integration
def test_waiting_referral_requires_linkedin(test_user):
    uid = test_user["id"]
    url = "https://example.com/jobs/ref"

    with pytest.raises(ValueError, match="LinkedIn"):
        set_job_waiting_referral_db(uid, "uk", "Acme", url, True)

    result = set_job_waiting_referral_db(
        uid,
        "uk",
        "Acme",
        url,
        True,
        linkedin_url="https://linkedin.com/in/test",
    )
    assert result["waiting_referral"] is True
    assert result["referral_linkedin_url"].startswith("https://linkedin.com")

    cleared = set_job_waiting_referral_db(uid, "uk", "Acme", url, False)
    assert cleared["waiting_referral"] is False


@pytest.mark.integration
def test_ats_score_set_and_clear(test_user):
    uid = test_user["id"]
    url = "https://example.com/jobs/ats"

    scored = set_job_ats_score_db(uid, "uk", "Acme", url, 85, job_title="Dev")
    assert scored["ats_score"] == 85

    cleared = set_job_ats_score_db(uid, "uk", "Acme", url, None)
    assert cleared["ats_score"] is None
    tracking = load_job_tracking(uid)
    assert tracking[("uk", "Acme", url)]["ats_score"] is None


@pytest.mark.integration
def test_company_awaiting_response_and_sync(test_user):
    uid = test_user["id"]
    company = "Sync Co"
    url = "https://example.com/jobs/sync"

    awaiting = set_company_awaiting_response_db(uid, "uk", company, True)
    assert awaiting["awaiting_response"] is True
    assert awaiting["awaiting_response_date"]

    preserved = set_company_awaiting_response_db(
        uid, "uk", company, True, preserve_date=True
    )
    assert preserved["awaiting_response"] is True

    set_job_applied_db(uid, "uk", company, url, True)
    sync = sync_company_applied_from_jobs_db(uid, "uk", company)
    assert sync["company_applied"] is True
    assert sync["positions_applied"] == 1

    set_job_applied_db(uid, "uk", company, url, False)
    sync_cleared = sync_company_applied_from_jobs_db(uid, "uk", company)
    assert sync_cleared["company_applied"] is False

    set_company_awaiting_response_db(uid, "uk", company, False)
    ct = load_company_tracking(uid)
    assert bool(ct[("uk", company)]["awaiting_response"]) is False


@pytest.mark.integration
def test_status_history_and_applied_today(test_user):
    uid = test_user["id"]
    url = "https://example.com/jobs/history"

    applied = set_job_applied_db(uid, "uk", "Hist Co", url, True, job_title="Eng")
    assert applied["applied_history"]
    assert applied.get("applied_at")

    set_job_rejected_db(uid, "uk", "Hist Co", url, True)
    history = load_job_status_history(uid)
    norm = normalize_job_url(url)
    bucket = history[("uk", "Hist Co", norm)]
    assert bucket["applied"]
    assert bucket["rejected"]
    assert bucket["applied_events"]
    assert bucket["rejected_events"]

    assert count_jobs_applied_db(uid) >= 1
    assert count_jobs_applied_db(uid, country="uk") >= 1
    assert count_jobs_applied_today_db(uid, timezone_name="UTC") >= 1
    assert count_jobs_applied_today_db(uid, country="uk", timezone_name="Europe/London") >= 1
    assert count_jobs_applied_today_db(uid, timezone_name="Invalid/TZ") >= 1


@pytest.mark.integration
def test_clear_and_rename_company_tracking(test_user):
    uid = test_user["id"]
    old_name = "Old Name Ltd"
    new_name = "New Name Ltd"
    url = "https://example.com/jobs/rename"

    set_job_applied_db(uid, "uk", old_name, url, True)
    set_company_applied_db(uid, "uk", old_name, True)

    rename_company_tracking("uk", old_name, new_name)
    tracking = load_job_tracking(uid)
    assert ("uk", new_name, url) in tracking
    assert ("uk", old_name, url) not in tracking
    assert ("uk", new_name) in load_company_tracking(uid)

    clear_company_tracking("uk", new_name)
    assert tracking_is_empty() or not any(
        k[1] == new_name for k in load_job_tracking(uid)
    )


@pytest.mark.integration
def test_migrate_tracking_from_json(db, tmp_data_dir, sample_country_data, monkeypatch):
    enriched = json.loads(json.dumps(sample_country_data))
    company = enriched["companies"][0]
    company["company_applied"] = True
    company["company_applied_date"] = "2025-06-01"
    job = company["matching_jobs"][0]
    job["applied"] = True
    job["applied_date"] = "2025-06-01"
    company["matching_jobs"][1]["rejected"] = True
    company["matching_jobs"][1]["rejected_date"] = "2025-06-02"

    def fake_load_country(key):
        return enriched if key == "uk" else None

    monkeypatch.setattr("relocation_jobs.catalog_db.load_country", fake_load_country)

    user = create_user("migrate_user", generate_password_hash("pass123456"))
    assert tracking_is_empty()
    written = migrate_tracking_from_json(user["id"])
    assert written >= 2
    assert not tracking_is_empty()


@pytest.mark.integration
def test_transaction_rollback(db):
    from relocation_jobs.db import db_transaction

    with pytest.raises(RuntimeError):
        with db_transaction() as conn:
            conn.execute("SELECT 1")
            raise RuntimeError("rollback test")


@pytest.mark.integration
def test_set_company_applied_direct(test_user):
    uid = test_user["id"]
    on = set_company_applied_db(uid, "uk", "Direct Co", True)
    assert on["company_applied"] is True
    off = set_company_applied_db(uid, "uk", "Direct Co", False)
    assert off["company_applied"] is False


@pytest.mark.integration
def test_applied_clears_looking_to_apply(test_user):
    uid = test_user["id"]
    url = "https://example.com/jobs/ltp"
    set_job_looking_to_apply_db(uid, "uk", "LTP Co", url, True)
    result = set_job_applied_db(uid, "uk", "LTP Co", url, True)
    assert result["looking_to_apply"] is False
