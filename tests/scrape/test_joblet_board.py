from __future__ import annotations

from relocation_jobs.scrape.boards.joblet import (
    joblet_board_url,
    parse_joblet_search_payload,
)


SAMPLE_PAYLOAD = {
    "success": True,
    "data": {
        "jobs": [
            {
                "id": "1",
                "title": "Senior Frontend Developer",
                "slug": "senior-frontend-developer-acme-abc123",
                "isRemote": True,
                "location": "Remote, United States",
                "employmentType": ["Full time"],
                "company": {"name": "Acme Labs"},
                "description": "<p>Build UI</p>",
                "applyUrl": "https://tnl2.jometer.com/v2/job?x=1",
            },
            {
                "id": "2",
                "title": "Office Manager",
                "slug": "office-manager-local-xyz",
                "isRemote": False,
                "location": "New York, NY",
                "employmentType": ["On-site"],
                "company": {"name": "LocalCo"},
                "applyUrl": "https://example.com/office",
            },
            {
                "id": "3",
                "title": "DevOps Engineer (Remote)",
                "url_slug": None,
                "isRemote": False,
                "location": "Berlin, Germany",
                "employmentType": ["Remote"],
                "company": {"name": "Orbit"},
                "applyUrl": "https://example.com/devops",
            },
            {
                "id": "4",
                "title": "Missing employer",
                "isRemote": True,
                "location": "Remote",
                "employmentType": ["Remote"],
                "company": {"name": ""},
                "applyUrl": "https://example.com/missing",
            },
        ]
    },
}


def test_joblet_board_url_defaults_and_preserves_host():
    assert joblet_board_url("") == "https://joblet.ai/jobs?employmentType=Remote"
    assert (
        joblet_board_url("https://joblet.ai/jobs")
        == "https://joblet.ai/jobs?employmentType=Remote"
    )
    assert (
        joblet_board_url("https://joblet.ai/jobs?employmentType=Remote")
        == "https://joblet.ai/jobs?employmentType=Remote"
    )
    assert joblet_board_url("https://example.com/x") == (
        "https://joblet.ai/jobs?employmentType=Remote"
    )


def test_parse_joblet_search_payload_keeps_remote_with_employer():
    jobs = parse_joblet_search_payload(SAMPLE_PAYLOAD)
    assert len(jobs) == 2
    by_title = {j["title"]: j for j in jobs}
    assert by_title["Senior Frontend Developer"]["employer"] == "Acme Labs"
    assert by_title["Senior Frontend Developer"]["url"] == (
        "https://joblet.ai/jobs/senior-frontend-developer-acme-abc123"
    )
    assert "Build UI" in by_title["Senior Frontend Developer"]["description_text"]
    assert by_title["DevOps Engineer (Remote)"]["employer"] == "Orbit"
    assert by_title["DevOps Engineer (Remote)"]["url"] == "https://example.com/devops"
