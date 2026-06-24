"""Business-rule workflow tests (rules 5–14) using v2 panel + positions only."""

from __future__ import annotations

import pytest

from relocation_jobs.core.job_identity import job_idempotency_key, normalize_job_url
from relocation_jobs.v2.panel.service import flatten_companies
from relocation_jobs.v2.positions import service as positions
from tests.v2.helpers.seed import merge_and_save_jobs, replace_matching_jobs


def _company_and_jobs(catalog: dict) -> tuple[str, str, str]:
    acme = catalog["companies"][0]
    company = acme["name"]
    url_a = acme["matching_jobs"][0]["url"]
    url_b = acme["matching_jobs"][1]["url"]
    return company, url_a, url_b


def _flatten(user_id: int, **kwargs):
    companies, _, _ = flatten_companies("uk", user_id=user_id, **kwargs)
    return companies


def _acme(companies: list[dict]) -> dict:
    return next(c for c in companies if c["name"] == "Acme Backend Ltd")


def _urls(jobs: list[dict]) -> set[str]:
    return {j["url"] for j in jobs}


@pytest.mark.integration
class TestApplyWorkflow:
    def test_apply_clears_looking_to_apply_and_sets_company_flags(
        self, seeded_catalog_v2, test_user
    ):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_looking_to_apply("uk", company, url, True, user_id=uid)
        positions.set_job_applied("uk", company, url, True, user_id=uid)

        acme = _acme(_flatten(uid))
        job = next(j for j in acme["jobs"] if j["url"] == url)

        assert job["applied"] is True
        assert job["looking_to_apply"] is False
        assert acme["awaiting_response"] is True
        assert acme["company_applied"] is True
        assert acme["positions_applied"] >= 1
        assert acme["positions_applied_all"] >= 1

    def test_apply_preserves_looking_to_apply_date(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        result = positions.set_job_looking_to_apply(
            "uk", company, url, True, user_id=uid,
        )
        assert result["looking_to_apply_date"]
        applied = positions.set_job_applied("uk", company, url, True, user_id=uid)

        assert applied["looking_to_apply"] is False
        assert applied["looking_to_apply_date"] == result["looking_to_apply_date"]

    def test_unapply_clears_applied_but_keeps_company_until_last_job(
        self, seeded_catalog_v2, test_user
    ):
        uid = test_user["id"]
        company, url_a, url_b = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_applied("uk", company, url_a, True, user_id=uid)
        positions.set_job_applied("uk", company, url_b, True, user_id=uid)
        positions.set_job_applied("uk", company, url_a, False, user_id=uid)

        acme = _acme(_flatten(uid))
        job_a = next(j for j in acme["jobs"] if j["url"] == url_a)
        job_b = next(j for j in acme["jobs"] if j["url"] == url_b)

        assert job_a["applied"] is False
        assert job_b["applied"] is True
        assert acme["company_applied"] is True


@pytest.mark.integration
class TestRejectAndReapply:
    def test_rejected_job_moves_to_rejected_list(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_rejected("uk", company, url, True, user_id=uid)
        acme = _acme(_flatten(uid))

        assert url not in _urls(acme["jobs"])
        assert url in _urls(acme["rejected_jobs"])
        assert acme["positions_rejected"] == 1

    def test_reapply_returns_job_to_main_list(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_rejected("uk", company, url, True, user_id=uid)
        positions.set_job_reapply("uk", company, url, user_id=uid)
        acme = _acme(_flatten(uid))

        assert url in _urls(acme["jobs"])
        assert url not in _urls(acme["rejected_jobs"])
        assert acme["positions_rejected"] == 0


@pytest.mark.integration
class TestPositionIsolation:
    def test_apply_one_job_does_not_mark_sibling(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url_a, url_b = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_applied("uk", company, url_b, True, user_id=uid)
        acme = _acme(_flatten(uid))

        job_a = next(j for j in acme["jobs"] if j["url"] == url_a)
        job_b = next(j for j in acme["jobs"] if j["url"] == url_b)

        assert job_a["applied"] is False
        assert job_b["applied"] is True

    def test_reject_one_job_does_not_mark_sibling(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url_a, url_b = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_rejected("uk", company, url_a, True, user_id=uid)
        acme = _acme(_flatten(uid))

        assert url_a in {j["url"] for j in acme["rejected_jobs"]}
        assert url_b in _urls(acme["jobs"])
        assert url_b not in {j["url"] for j in acme["rejected_jobs"]}


@pytest.mark.integration
class TestPositionFilters:
    def test_looking_to_apply_only_filter(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, other = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_looking_to_apply("uk", company, url, True, user_id=uid)
        companies = _flatten(uid, position_looking_to_apply_only=True)
        acme = _acme(companies)

        assert url in _urls(acme["jobs"])
        assert other not in _urls(acme["jobs"])


@pytest.mark.integration
class TestNotForMe:
    def test_not_for_me_removed_from_main_jobs_bucket(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, other = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_not_for_me("uk", company, url, user_id=uid, not_for_me=True)
        acme = _acme(_flatten(uid))

        assert url not in _urls(acme["jobs"])
        assert url in _urls(acme["not_for_me_jobs"])
        assert other in _urls(acme["jobs"])
        assert acme["positions_not_for_me"] == 1

    def test_clear_not_for_me_returns_job_to_main_list(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_not_for_me("uk", company, url, user_id=uid, not_for_me=True)
        positions.set_job_not_for_me("uk", company, url, user_id=uid, not_for_me=False)
        acme = _acme(_flatten(uid))

        assert url in _urls(acme["jobs"])
        assert url not in _urls(acme["not_for_me_jobs"])


@pytest.mark.integration
class TestUrlAliasTracking:
    def test_applied_via_tracking_alias_shows_on_catalog_url(
        self, seeded_catalog_v2, test_user
    ):
        uid = test_user["id"]
        company, canonical, _ = _company_and_jobs(seeded_catalog_v2)
        alias = (
            "https://www.boards.greenhouse.io/acmebackend/jobs/123456"
            "?gh_jid=123456&utm_source=linkedin"
        )
        assert job_idempotency_key(alias) == job_idempotency_key(canonical)

        positions.set_job_applied("uk", company, alias, True, user_id=uid)
        acme = _acme(_flatten(uid))
        job = next(j for j in acme["jobs"] if j["url"] == canonical)

        assert job["applied"] is True
        assert job["applied_date"]


@pytest.mark.integration
class TestOrphanTrackedJobs:
    def test_applied_job_persists_after_removed_from_catalog(
        self, seeded_catalog_v2, test_user
    ):
        uid = test_user["id"]
        company, url, other_url = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_applied("uk", company, url, True, user_id=uid)

        replace_matching_jobs(
            "uk",
            company,
            [j for j in seeded_catalog_v2["companies"][0]["matching_jobs"] if j["url"] != url],
        )

        acme = _acme(_flatten(uid))
        tracked = next(
            j for j in acme["jobs"]
            if normalize_job_url(j["url"]) == normalize_job_url(url)
        )

        assert tracked["applied"] is True
        assert tracked["title"]
        assert other_url in _urls(acme["jobs"])

    def test_rejected_orphan_appears_in_rejected_jobs(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_rejected("uk", company, url, True, user_id=uid)

        replace_matching_jobs(
            "uk",
            company,
            [j for j in seeded_catalog_v2["companies"][0]["matching_jobs"] if j["url"] != url],
        )

        acme = _acme(_flatten(uid))
        assert normalize_job_url(url) in {
            normalize_job_url(j["url"]) for j in acme["rejected_jobs"]
        }


@pytest.mark.integration
class TestListFilters:
    def test_hide_position_applied_excludes_applied_jobs_only(
        self, seeded_catalog_v2, test_user
    ):
        uid = test_user["id"]
        company, url_a, url_b = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_applied("uk", company, url_a, True, user_id=uid)
        acme = _acme(_flatten(uid, hide_position_applied=True))

        assert url_a not in _urls(acme["jobs"])
        assert url_b in _urls(acme["jobs"])
        assert acme["company_applied"] is True

    def test_position_applied_only_shows_applied_jobs(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url_a, url_b = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_applied("uk", company, url_a, True, user_id=uid)
        acme = _acme(_flatten(uid, position_applied_only=True))

        assert _urls(acme["jobs"]) == {url_a}
        assert url_b not in _urls(acme["jobs"])

    def test_position_rejected_only_shows_rejected_bucket(
        self, seeded_catalog_v2, test_user
    ):
        uid = test_user["id"]
        company, url_a, url_b = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_rejected("uk", company, url_a, True, user_id=uid)
        acme = _acme(_flatten(uid, position_rejected_only=True))

        assert url_a in _urls(acme["rejected_jobs"])
        assert url_b not in _urls(acme["jobs"])
        assert url_b not in _urls(acme["rejected_jobs"])

    def test_hide_applied_hides_entire_company(self, seeded_catalog_v2, test_user):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_applied("uk", company, url, True, user_id=uid)
        companies = _flatten(uid, hide_applied=True)

        assert not any(c["name"] == company for c in companies)


@pytest.mark.integration
class TestScrapeMergeVsDbOverlay:
    def test_catalog_rescrape_does_not_clear_db_applied_state(
        self, seeded_catalog_v2, test_user
    ):
        uid = test_user["id"]
        company, url, _ = _company_and_jobs(seeded_catalog_v2)

        positions.set_job_applied("uk", company, url, True, user_id=uid)

        merge_and_save_jobs(
            "uk",
            company,
            [{"title": "Senior Backend Engineer (updated title)", "url": url}],
        )

        acme = _acme(_flatten(uid))
        job = next(j for j in acme["jobs"] if j["url"] == url)

        assert job["applied"] is True
        assert "updated title" in job["title"]
