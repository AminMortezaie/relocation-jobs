from __future__ import annotations

import pytest

from relocation_jobs.scrape.filter import filter_relevant_jobs
from relocation_jobs.scrape.relevance import is_relevant


class TestIsRelevant:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Senior Backend Engineer", True),
            ("Software Developer", True),
            ("Chief Technology Officer", False),
            ("Marketing Manager", False),
            ("Staff Software Engineer", False),
            ("Senior Python Engineer", True),
            ("Senior Python AI Engineer", True),
            ("Senior Python Engineer- GenAI", True),
        ],
    )
    def test_title_gate(self, title: str, expected: bool):
        assert is_relevant(title) is expected

    def test_filter_relevant_jobs_strips_non_backend(self):
        jobs = [
            {"title": "Backend Engineer", "url": "https://example.com/1"},
            {"title": "Marketing Manager", "url": "https://example.com/2"},
        ]
        out = filter_relevant_jobs(jobs, relevant_only=True)
        assert len(out) == 1
        assert out[0]["title"] == "Backend Engineer"

    def test_filter_relevant_jobs_keeps_all_when_disabled(self):
        jobs = [
            {"title": "Backend Engineer", "url": "https://example.com/1"},
            {"title": "Marketing Manager", "url": "https://example.com/2"},
        ]
        out = filter_relevant_jobs(jobs, relevant_only=False)
        assert len(out) == 2
