"""Pure scrape logic: relevance filter, job merge, static ATS URL detection."""

from relocation_jobs.core.ats_detection import (
    _follow_meta_refresh,
    detect_ats_static,
)
from relocation_jobs.scrape_jobs import (
    explain_title_filter,
    is_relevant,
    merge_matching_jobs,
    _review_entry,
    _review_filtered_jobs,
)


class TestIsRelevant:
    def test_accepts_backend_engineer(self):
        assert is_relevant("Senior Backend Engineer")

    def test_rejects_marketing_for_non_engineer_roles(self):
        assert not is_relevant("Marketing Manager")

    def test_allows_engineer_with_marketing_team_suffix(self):
        assert is_relevant("Fullstack Engineer – Marketing")

    def test_rejects_cto(self):
        assert not is_relevant("Chief Technology Officer")
        assert not is_relevant("CTO")

    def test_rejects_cloud_engineer_without_backend_or_software(self):
        assert not is_relevant("Cloud Engineer")
        assert is_relevant("Backend Cloud Engineer")

    def test_explain_title_filter_salesforce_developer(self):
        title = "Senior Developer - Salesforce Marketing Cloud"
        assert not is_relevant(title)
        assert explain_title_filter(title) == "Title not relevant (no backend/software keyword)"

    def test_explain_title_filter_cto(self):
        assert explain_title_filter("Chief Technology Officer") == "Title excluded (CTO)"


class TestReviewFilteredJobs:
    def test_review_filtered_jobs_title_and_location_reasons(self):
        company = {
            "locations": [{"country": "germany", "city": "Berlin"}],
        }
        all_scraped = [
            {"title": "Backend Engineer", "url": "https://example.com/j/1", "location": "Berlin, Germany"},
            {"title": "Senior Developer - Salesforce", "url": "https://example.com/j/2"},
            {
                "title": "Software Engineer",
                "url": "https://example.com/j/3",
                "location": "Kochi, India",
            },
        ]
        scraped = [all_scraped[0]]
        filtered = _review_filtered_jobs(all_scraped, scraped, company, catalog_country="germany")
        by_url = {job["url"]: job["filter_reason"] for job in filtered}
        assert by_url["https://example.com/j/2"].startswith("Title not relevant")
        assert "india" in by_url["https://example.com/j/3"].lower()

    def test_review_entry_includes_filter_reason(self):
        entry = _review_entry({
            "title": "Marketing Manager",
            "url": "https://example.com/j/2",
            "filter_reason": "Title excluded (marketing)",
        })
        assert entry["filter_reason"] == "Title excluded (marketing)"


class TestMergeMatchingJobs:
    def test_preserves_existing_jobs_and_adds_new(self):
        existing = [
            {
                "title": "Old Title",
                "url": "https://example.com/j/1?gh_jid=1",
                "fetched": "2025-01-01",
                "applied": True,
            }
        ]
        scraped = [
            {
                "title": "Updated Title",
                "url": "https://example.com/j/1?gh_jid=1",
            },
            {
                "title": "Brand New Role",
                "url": "https://example.com/j/2?gh_jid=2",
            },
        ]
        merged, preserved, new_count, stale = merge_matching_jobs(existing, scraped)
        assert len(merged) == 2
        assert preserved == 1
        assert new_count == 1
        assert stale == 0

        by_url = {j["url"]: j for j in merged}
        kept = by_url["https://example.com/j/1?gh_jid=1"]
        assert kept["fetched"] == "2025-01-01"
        assert kept["applied"] is True
        assert kept["title"] == "Updated Title"

    def test_keeps_stale_jobs_not_in_scrape(self):
        existing = [
            {"title": "Gone Role", "url": "https://example.com/j/99?gh_jid=99", "fetched": "2024-01-01"},
        ]
        scraped = [
            {"title": "New Role", "url": "https://example.com/j/1?gh_jid=1"},
        ]
        merged, preserved, new_count, stale = merge_matching_jobs(existing, scraped)
        assert len(merged) == 2
        assert preserved == 0
        assert new_count == 1
        assert stale == 1


class TestDetectAtsStatic:
    def test_detects_greenhouse_from_html(self, monkeypatch):
        response = type("R", (), {"text": "https://boards.greenhouse.io/acme", "url": "https://example.com/careers"})()
        monkeypatch.setattr(
            "relocation_jobs.scrape_jobs.requests.get",
            lambda *args, **kwargs: response,
        )
        ats_type, ats_url = detect_ats_static("https://example.com/careers")
        assert ats_type == "greenhouse"
        assert "acme" in ats_url

    def test_detects_lever_eu_from_html(self, monkeypatch):
        response = type("R", (), {"text": "https://jobs.eu.lever.co/acme", "url": "https://example.com/careers"})()
        monkeypatch.setattr(
            "relocation_jobs.scrape_jobs.requests.get",
            lambda *args, **kwargs: response,
        )
        ats_type, ats_url = detect_ats_static("https://example.com/careers")
        assert ats_type == "lever_eu"
        assert "acme" in ats_url

    def test_detects_workday_from_careers_html(self, monkeypatch):
        html = (
            '<a href="https://swisscom.wd103.myworkdayjobs.com/de-DE/'
            'SwisscomExternalCareers">Jobs</a>'
        )
        response = type("R", (), {"text": html, "url": "https://example.com/careers"})()
        monkeypatch.setattr(
            "relocation_jobs.scrape_jobs.requests.get",
            lambda *args, **kwargs: response,
        )
        ats_type, ats_url = detect_ats_static("https://example.com/careers")
        assert ats_type == "workday"
        assert "SwisscomExternalCareers" in ats_url

    def test_follows_meta_refresh_to_workday(self, monkeypatch):
        calls: list[str] = []

        def fake_get(url, **kwargs):
            calls.append(url)
            if url.endswith("/jobs/"):
                return type(
                    "R",
                    (),
                    {
                        "text": (
                            '<meta http-equiv="Refresh" content="0; '
                            'url=https://example.com/karriere.html">'
                        ),
                        "url": url,
                    },
                )()
            return type(
                "R",
                (),
                {
                    "text": (
                        "https://swisscom.wd103.myworkdayjobs.com/de-DE/"
                        "SwisscomExternalCareers"
                    ),
                    "url": url,
                },
            )()

        monkeypatch.setattr("relocation_jobs.scrape_jobs.requests.get", fake_get)
        ats_type, ats_url = detect_ats_static("https://example.com/jobs/")
        assert len(calls) == 2
        assert ats_type == "workday"
        assert "SwisscomExternalCareers" in ats_url

    def test_meta_refresh_helper(self):
        html = '<meta http-equiv="Refresh" content="0; url=/karriere.html">'
        assert _follow_meta_refresh(html, "https://example.com/jobs/") == (
            "https://example.com/karriere.html"
        )
