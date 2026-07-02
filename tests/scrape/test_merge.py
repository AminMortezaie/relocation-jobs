from __future__ import annotations

from relocation_jobs.scrape.merge import merge_matching_jobs


class TestMergeMatchingJobs:
    def test_merges_visa_from_scrape_when_missing(self):
        existing = [
            {"title": "Old", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"},
        ]
        scraped = [
            {
                "title": "New Title",
                "url": "https://example.com/j/1?gh_jid=1",
                "visa_sponsorship": True,
            },
        ]
        merged, preserved, new_count, stale, new_jobs = merge_matching_jobs(existing, scraped)
        assert preserved == 1
        assert new_count == 0
        assert stale == 0
        assert new_jobs == []
        assert merged[0]["visa_sponsorship"] is True
        assert merged[0]["title"] == "New Title"
        assert merged[0]["fetched"] == "2025-01-01"

    def test_keeps_stale_jobs_not_in_latest_scrape(self):
        existing = [
            {"title": "Gone", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"},
        ]
        merged, preserved, new_count, stale, new_jobs = merge_matching_jobs(existing, [])
        assert preserved == 0
        assert new_count == 0
        assert stale == 1
        assert new_jobs == []
        assert len(merged) == 1
        assert merged[0]["title"] == "Gone"

    def test_deduplicates_existing_by_earliest_fetched(self):
        existing = [
            {"title": "A", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-02-01"},
            {"title": "B", "url": "https://example.com/j/1?gh_jid=1", "fetched": "2025-01-01"},
        ]
        scraped = [{"title": "C", "url": "https://example.com/j/2?gh_jid=2"}]
        merged, _, new_count, _, new_jobs = merge_matching_jobs(existing, scraped)
        assert new_count == 1
        assert len(new_jobs) == 1
        preserved = [j for j in merged if "j/1" in j["url"]][0]
        assert preserved["fetched"] == "2025-01-01"

    def test_updates_last_seen_on_rescrape(self):
        existing = [
            {
                "title": "Old",
                "url": "https://example.com/j/1?gh_jid=1",
                "fetched": "2025-01-01",
                "last_seen": "2025-01-01T00:00:00+00:00",
            },
        ]
        scraped = [{"title": "New Title", "url": "https://example.com/j/1?gh_jid=1"}]
        merged, preserved, new_count, stale, new_jobs = merge_matching_jobs(existing, scraped)
        assert preserved == 1
        assert new_count == 0
        assert new_jobs == []
        assert merged[0]["fetched"] == "2025-01-01"
        assert merged[0]["last_seen"] != "2025-01-01T00:00:00+00:00"
