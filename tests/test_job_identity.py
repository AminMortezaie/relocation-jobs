"""Stable job URL identity — merge keys must survive tracking params and host variants."""

from relocation_jobs.job_identity import (
    backfill_job_identities,
    is_idempotency_hash,
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
    stamp_job_identity,
)


def test_normalize_job_url_strips_tracking_and_www():
    raw = "HTTPS://WWW.Example.com/jobs/123?utm_source=linkedin&gh_jid=123#apply"
    assert normalize_job_url(raw) == "https://example.com/jobs/123?gh_jid=123"


def test_same_job_different_hosts_produces_same_key():
    a = "https://boards.greenhouse.io/acme/jobs/1?gh_jid=1"
    b = "https://www.boards.greenhouse.io/acme/jobs/1?gh_jid=1&utm=foo"
    assert job_idempotency_key(a) == job_idempotency_key(b)


def test_different_jobs_produce_different_keys():
    a = job_idempotency_key("https://example.com/jobs/1?gh_jid=1")
    b = job_idempotency_key("https://example.com/jobs/2?gh_jid=2")
    assert a and b and a != b


def test_idempotency_key_is_stable_sha256_hex():
    key = job_idempotency_key("https://example.com/jobs/1?gh_jid=1")
    assert is_idempotency_hash(key)
    assert len(key) == 64


def test_stamp_and_backfill_identities():
    data = {
        "companies": [
            {
                "matching_jobs": [
                    {"title": "Engineer", "url": "https://example.com/j/1?gh_jid=1"},
                ]
            }
        ]
    }
    updated = backfill_job_identities(data)
    job = data["companies"][0]["matching_jobs"][0]
    assert updated == 1
    assert job["idempotency_key"] == job_idempotency_key(job["url"])
    assert backfill_job_identities(data) == 0

    stamped = stamp_job_identity({"url": "https://example.com/j/2?gh_jid=2"})
    assert stamped["idempotency_key"] == job_idempotency_key(stamped["url"])


def test_normalize_job_url_empty_and_root_path():
    assert normalize_job_url("") == ""
    assert normalize_job_url("   ") == ""
    assert normalize_job_url("https://example.com") == "https://example.com/"


def test_job_idempotency_key_empty_url():
    assert job_idempotency_key("") == ""
    assert job_idempotency_key_for_job({"url": ""}) == ""


def test_backfill_skips_existing_hash():
    key = job_idempotency_key("https://example.com/j/1?gh_jid=1")
    data = {"companies": [{"matching_jobs": [{"url": "https://example.com/j/1?gh_jid=1", "idempotency_key": key}]}]}
    assert backfill_job_identities(data) == 0
