from __future__ import annotations

from relocation_jobs.scrape.boards.bol import (
    bol_jobs_path_prefix,
    bol_search_payload,
    parse_bol_response,
)


def test_bol_search_payload_uses_page_number():
    payload = bol_search_payload("https://careers.bol.com/en/jobs/", page=3)
    assert payload["page"] == 3
    assert payload["jobFamily"] == []


def test_bol_jobs_path_prefix_nl():
    assert bol_jobs_path_prefix("https://careers.bol.com/nl/vacatures/") == (
        "https://careers.bol.com/nl/vacatures"
    )


def test_parse_bol_response_builds_stable_job_urls():
    data = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_source": {
                        "id": 8620597002,
                        "title": "Senior Offensive Security Engineer",
                        "office": {"label": "Utrecht"},
                    }
                }
            ],
        }
    }
    jobs = parse_bol_response(data, path_prefix="https://careers.bol.com/en/jobs")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Offensive Security Engineer"
    assert jobs[0]["url"] == "https://careers.bol.com/en/jobs/_/8620597002/"
    assert jobs[0]["location"] == "Utrecht"
