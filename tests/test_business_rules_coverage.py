"""
End-to-end tests mapped to tests/BUSINESS_RULES.md (rules 1–16).

Each test class references the rule number(s) it locks in.
"""

from __future__ import annotations

import copy

import pytest
from werkzeug.security import generate_password_hash

from relocation_jobs.catalog_db import load_country, save_country
from relocation_jobs.db import create_user, load_job_status_history
from relocation_jobs.job_identity import job_idempotency_key, normalize_job_url
from relocation_jobs.location_tags import filter_jobs_by_expected_locations
from relocation_jobs.panel_data import (
    flatten_companies,
    set_company_applied,
    set_job_applied,
    set_job_ats_score,
    set_job_looking_to_apply,
    set_job_not_for_me,
    set_job_rejected,
    set_job_seen,
    set_job_waiting_referral,
)
from relocation_jobs.scrape_jobs import is_relevant, merge_matching_jobs


@pytest.fixture
def rich_catalog(seeded_catalog, sample_country_data):
    data = copy.deepcopy(sample_country_data)
    acme = data["companies"][0]
    acme["matching_jobs"][0]["visa_sponsorship"] = True
    acme["matching_jobs"][1]["visa_sponsorship"] = False
    acme["locations"] = [{"country": "uk", "city": "London"}]
    data["companies"].append(
        {
            "name": "Empty Corp",
            "city": "Manchester",
            "locations": [{"country": "uk", "city": "Manchester"}],
            "careers_url": "https://example.co.uk/empty",
            "matching_jobs": [],
        }
    )
    save_country("uk", data, export_archive=False)
    return data


def _jobs(state_catalog):
    acme = state_catalog["companies"][0]
    return acme["name"], acme["matching_jobs"][0]["url"], acme["matching_jobs"][1]["url"]


def _flatten(user_id: int | None = None, **kwargs):
    return flatten_companies("uk", user_id=user_id, **kwargs)[0]


def _acme(companies):
    return next(c for c in companies if c["name"] == "Acme Backend Ltd")


def _urls(rows):
    return {r["url"] for r in rows}


# Rule 1 — catalog vs tracking
@pytest.mark.integration
class TestRule01CatalogVsTracking:
    def test_without_user_id_ignores_db_tracking(self, rich_catalog, test_user):
        company, url_a, _ = _jobs(rich_catalog)
        set_job_applied("uk", company, url_a, True, user_id=test_user["id"])

        acme = _acme(_flatten(user_id=None))
        job = next(j for j in acme["jobs"] if j["url"] == url_a)
        assert job["applied"] is False

    def test_with_user_id_overlays_db_tracking(self, rich_catalog, test_user):
        company, url_a, _ = _jobs(rich_catalog)
        set_job_applied("uk", company, url_a, True, user_id=test_user["id"])

        acme = _acme(_flatten(user_id=test_user["id"]))
        job = next(j for j in acme["jobs"] if j["url"] == url_a)
        assert job["applied"] is True


# Rule 2 — scrape never deletes
@pytest.mark.integration
class TestRule02ScrapeNeverDeletes:
    def test_merge_keeps_stale_jobs_missing_from_scrape(self):
        existing = [
            {"title": "Stale Role", "url": "https://example.com/j/99?gh_jid=99", "fetched": "2024-01-01"},
            {"title": "Live Role", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2024-06-01"},
        ]
        scraped = [{"title": "Live Role Updated", "url": "https://example.com/j/1?gh_jid=1"}]
        merged, _, new_count, stale = merge_matching_jobs(existing, scraped)

        urls = {j["url"] for j in merged}
        assert "https://example.com/j/99?gh_jid=99" in urls
        assert stale == 1
        assert new_count == 0
        stale_job = next(j for j in merged if "99" in j["url"])
        assert stale_job["fetched"] == "2024-01-01"


# Rule 3 — tracking survives re-scrape (DB overlay)
@pytest.mark.integration
class TestRule03TrackingSurvivesRescrape:
    def test_rejected_state_survives_catalog_title_update(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)
        set_job_rejected("uk", company, url, True, user_id=uid)

        data = copy.deepcopy(load_country("uk"))
        blob = data["companies"][0]
        merged, _, _, _ = merge_matching_jobs(
            blob["matching_jobs"],
            [{"title": "Renamed", "url": url}],
        )
        blob["matching_jobs"] = merged
        save_country("uk", data, export_archive=False)

        acme = _acme(_flatten(uid))
        assert url in _urls(acme["rejected_jobs"])
        assert url not in _urls(acme["jobs"])


# Rule 4 — one role one key (alias on read)
@pytest.mark.integration
class TestRule04JobIdentity:
    def test_seen_via_alias_url_on_canonical_catalog_row(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, canonical, _ = _jobs(rich_catalog)
        alias = canonical.replace("https://", "https://www.") + "&utm=x"
        assert job_idempotency_key(alias) == job_idempotency_key(canonical)

        set_job_seen("uk", company, alias, True, user_id=uid)
        acme = _acme(_flatten(uid))
        job = next(j for j in acme["jobs"] if j["url"] == canonical)
        assert job["seen"] is True


# Rule 5 — apply side effects
@pytest.mark.integration
class TestRule05Apply:
    def test_apply_records_status_history(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)
        result = set_job_applied("uk", company, url, True, user_id=uid)

        assert result["applied"] is True
        assert result.get("applied_history")
        history = load_job_status_history(uid)
        key = ("uk", company, normalize_job_url(url))
        assert history[key]["applied"]


# Rule 6 — unapply keeps awaiting_response
@pytest.mark.integration
class TestRule06Unapply:
    def test_unapply_last_job_keeps_awaiting_response(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)

        set_job_applied("uk", company, url, True, user_id=uid)
        acme = _acme(_flatten(uid))
        assert acme["awaiting_response"] is True

        set_job_applied("uk", company, url, False, user_id=uid)
        acme = _acme(_flatten(uid))
        assert acme["company_applied"] is False
        assert acme["awaiting_response"] is True


# Rule 7 — reject does not clear applied
@pytest.mark.integration
class TestRule07Reject:
    def test_reject_after_apply_keeps_applied_flag(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)

        set_job_applied("uk", company, url, True, user_id=uid)
        set_job_rejected("uk", company, url, True, user_id=uid)

        acme = _acme(_flatten(uid))
        rejected = next(j for j in acme["rejected_jobs"] if j["url"] == url)
        assert rejected["applied"] is True
        assert rejected["rejected"] is True
        assert url not in _urls(acme["jobs"])


# Rule 8 — not for me orphans not reinjected
@pytest.mark.integration
class TestRule08NotForMe:
    def test_not_for_me_orphan_not_reinjected(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, other = _jobs(rich_catalog)

        set_job_not_for_me("uk", company, url, user_id=uid, not_for_me=True)

        data = copy.deepcopy(load_country("uk"))
        data["companies"][0]["matching_jobs"] = [
            j for j in data["companies"][0]["matching_jobs"] if j["url"] != url
        ]
        save_country("uk", data, export_archive=False)

        acme = _acme(_flatten(uid))
        assert url not in _urls(acme["jobs"])
        assert url not in _urls(acme["not_for_me_jobs"])
        assert other in _urls(acme["jobs"])


# Rule 9 — waiting for referral
@pytest.mark.integration
class TestRule09WaitingReferral:
    def test_waiting_referral_requires_linkedin_and_shows_on_panel(
        self, rich_catalog, test_user
    ):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)

        with pytest.raises(ValueError, match="LinkedIn"):
            set_job_waiting_referral("uk", company, url, True, user_id=uid)

        set_job_waiting_referral(
            "uk",
            company,
            url,
            True,
            user_id=uid,
            linkedin_url="https://linkedin.com/in/referrer",
        )
        acme = _acme(_flatten(uid))
        job = next(j for j in acme["jobs"] if j["url"] == url)
        assert job["waiting_referral"] is True
        assert "linkedin.com" in job["referral_linkedin_url"]


# Rule 10 — three buckets (rejected wins)
@pytest.mark.integration
class TestRule10ThreeBuckets:
    def test_rejected_job_never_in_main_jobs_list(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, other = _jobs(rich_catalog)

        set_job_rejected("uk", company, url, True, user_id=uid)
        acme = _acme(_flatten(uid))

        assert url in _urls(acme["rejected_jobs"])
        assert url not in _urls(acme["jobs"])
        assert url not in _urls(acme["not_for_me_jobs"])
        assert other in _urls(acme["jobs"])


# Rule 11 — orphan reinjection (looking to apply)
@pytest.mark.integration
class TestRule11OrphanReinjection:
    def test_looking_to_apply_orphan_reinjected(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)

        set_job_looking_to_apply("uk", company, url, True, user_id=uid)

        data = copy.deepcopy(load_country("uk"))
        data["companies"][0]["matching_jobs"] = [
            j for j in data["companies"][0]["matching_jobs"] if j["url"] != url
        ]
        save_country("uk", data, export_archive=False)

        acme = _acme(_flatten(uid))
        orphan = next(
            j for j in acme["jobs"]
            if normalize_job_url(j["url"]) == normalize_job_url(url)
        )
        assert orphan["looking_to_apply"] is True


# Rule 12 — company applied derived + manual
@pytest.mark.integration
class TestRule12CompanyApplied:
    def test_derived_from_orphan_applied_job(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)

        set_job_applied("uk", company, url, True, user_id=uid)
        data = copy.deepcopy(load_country("uk"))
        data["companies"][0]["matching_jobs"] = []
        save_country("uk", data, export_archive=False)

        acme = _acme(_flatten(uid))
        assert acme["company_applied"] is True
        assert acme["positions_applied_all"] >= 1

    def test_manual_company_applied_stored_in_db_derived_on_read_from_jobs(
        self, rich_catalog, test_user
    ):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)

        set_company_applied("uk", company, True, user_id=uid)
        from relocation_jobs.db import load_company_tracking

        ct = load_company_tracking(uid)
        assert bool(ct[("uk", company)]["company_applied"]) is True

        acme = _acme(_flatten(uid))
        assert acme["company_applied"] is False

        set_job_applied("uk", company, url, True, user_id=uid)
        acme = _acme(_flatten(uid))
        assert acme["company_applied"] is True


# Rule 13 — company vs position filters
@pytest.mark.integration
class TestRule13FiltersCompanyVsPosition:
    def test_hide_position_rejected_does_not_hide_rejected_bucket(
        self, rich_catalog, test_user
    ):
        """Rejected rows live in rejected_jobs before position filters run."""
        uid = test_user["id"]
        company, url_a, url_b = _jobs(rich_catalog)

        set_job_rejected("uk", company, url_a, True, user_id=uid)
        acme = _acme(_flatten(uid, hide_position_rejected=True))

        assert url_a in _urls(acme["rejected_jobs"])
        assert url_b in _urls(acme["jobs"])

    def test_position_looking_to_apply_only(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url_a, url_b = _jobs(rich_catalog)

        set_job_looking_to_apply("uk", company, url_a, True, user_id=uid)
        acme = _acme(_flatten(uid, position_looking_to_apply_only=True))

        assert _urls(acme["jobs"]) == {url_a}
        assert url_b not in _urls(acme["jobs"])


# Rule 14 — other list filters
@pytest.mark.integration
class TestRule14OtherFilters:
    def test_visa_only_excludes_non_visa_jobs(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url_visa, url_no_visa = _jobs(rich_catalog)

        acme = _acme(_flatten(uid, visa_only=True))
        urls = _urls(acme["jobs"])
        assert url_visa in urls
        assert url_no_visa not in urls

    def test_hide_empty_drops_companies_with_no_visible_jobs(self, rich_catalog, test_user):
        companies = _flatten(test_user["id"], hide_empty=True)
        names = {c["name"] for c in companies}
        assert "Empty Corp" not in names
        assert "Acme Backend Ltd" in names

    def test_not_applied_only_excludes_company_with_applied_job(
        self, rich_catalog, test_user
    ):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)

        set_job_applied("uk", company, url, True, user_id=uid)
        names = {c["name"] for c in _flatten(uid, not_applied_only=True)}
        assert company not in names


# Rule 15 — backend relevance
class TestRule15BackendRelevance:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Senior Backend Engineer", True),
            ("Chief Technology Officer", False),
            ("Marketing Manager", False),
            ("Fullstack Engineer – Marketing", True),
        ],
    )
    def test_is_relevant_gate(self, title, expected):
        assert is_relevant(title) is expected


# Rule 16 — location gate
class TestRule16LocationGate:
    def test_job_outside_tagged_city_excluded(self):
        company = {
            "locations": [{"country": "uk", "city": "London"}],
        }
        jobs = [
            {"title": "Backend Engineer", "url": "https://x/1", "location": "Berlin, Germany"},
            {"title": "Backend Engineer", "url": "https://x/2", "location": "London, UK"},
        ]
        kept, skipped = filter_jobs_by_expected_locations(jobs, company, catalog_country="uk")
        assert len(kept) == 1
        assert kept[0]["url"] == "https://x/2"
        assert skipped

    @pytest.mark.integration
    def test_wrong_location_hidden_from_main_job_list(self, db, sample_country_data):
        from relocation_jobs.catalog_db import save_country
        from relocation_jobs.panel_data import flatten_companies

        company = sample_country_data["companies"][0]
        company["locations"] = [{"country": "uk", "city": "London"}]
        company["matching_jobs"] = [
            {"title": "Ok", "url": "https://x/ok", "location": "London, UK"},
            {"title": "Far", "url": "https://x/far", "location": "Paris, France"},
        ]
        save_country("uk", sample_country_data, export_archive=False)

        companies, _, _ = flatten_companies("uk")
        acme = companies[0]
        assert [j["url"] for j in acme["jobs"]] == ["https://x/ok"]
        assert acme["not_for_me_jobs"][0]["not_for_me_reason"] == "wrong_location"


# Extra: ATS score + multi-user isolation
@pytest.mark.integration
class TestAdditionalState:
    def test_ats_score_on_panel_read(self, rich_catalog, test_user):
        uid = test_user["id"]
        company, url, _ = _jobs(rich_catalog)
        set_job_ats_score("uk", company, url, 77, user_id=uid)

        acme = _acme(_flatten(uid))
        job = next(j for j in acme["jobs"] if j["url"] == url)
        assert job["ats_score"] == 77

    def test_tracking_isolated_per_user(self, rich_catalog, db):
        from relocation_jobs.db import create_user

        user_a = create_user("user_a", generate_password_hash("pass123456"))
        user_b = create_user("user_b", generate_password_hash("pass123456"))
        company, url, _ = _jobs(rich_catalog)

        set_job_applied("uk", company, url, True, user_id=user_a["id"])

        acme_a = _acme(_flatten(user_a["id"]))
        acme_b = _acme(_flatten(user_b["id"]))
        job_a = next(j for j in acme_a["jobs"] if j["url"] == url)
        job_b = next(j for j in acme_b["jobs"] if j["url"] == url)

        assert job_a["applied"] is True
        assert job_b["applied"] is False


# API smoke — state mutations round-trip through HTTP
@pytest.mark.integration
class TestRuleApiRoundTrip:
    def test_apply_via_api_reflected_in_jobs_list(self, auth_client, rich_catalog, test_user):
        resp = auth_client.get("/api/jobs?country=uk")
        job = resp.get_json()["companies"][0]["jobs"][0]

        applied = auth_client.post(
            "/api/jobs/applied",
            json={
                "country": "uk",
                "company": job["company"],
                "url": job["url"],
                "applied": True,
            },
        )
        assert applied.status_code == 200

        refreshed = auth_client.get("/api/jobs?country=uk")
        updated = next(
            j
            for j in refreshed.get_json()["companies"][0]["jobs"]
            if j["url"] == job["url"]
        )
        assert updated["applied"] is True

    def test_not_for_me_via_api(self, auth_client, rich_catalog, test_user):
        resp = auth_client.get("/api/jobs?country=uk")
        job = resp.get_json()["companies"][0]["jobs"][0]

        nfm = auth_client.post(
            "/api/jobs/not-for-me",
            json={
                "country": "uk",
                "company": job["company"],
                "url": job["url"],
                "not_for_me": True,
                "reason": "stack",
            },
        )
        assert nfm.status_code == 200

        refreshed = auth_client.get("/api/jobs?country=uk")
        acme = refreshed.get_json()["companies"][0]
        assert job["url"] not in {j["url"] for j in acme["jobs"]}
        assert job["url"] in {j["url"] for j in acme["not_for_me_jobs"]}
