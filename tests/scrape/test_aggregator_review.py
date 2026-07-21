from __future__ import annotations

from relocation_jobs.scrape.review import build_review_payload, review_filtered_jobs


def test_aggregator_review_lists_filtered_with_employer():
    raw = [
        {
            "title": "Senior Backend Engineer",
            "url": "https://remoteOK.com/remote-jobs/acme-1",
            "employer": "Acme",
        },
        {
            "title": "Principal Software Engineer",
            "url": "https://remoteOK.com/remote-jobs/orbit-2",
            "employer": "Orbit",
        },
        {
            "title": "Sales Director",
            "url": "https://remoteOK.com/remote-jobs/sales-3",
            "employer": "SalesCo",
        },
    ]
    from relocation_jobs.scrape.filter import filter_relevant_jobs

    matched = filter_relevant_jobs(raw, True)
    filtered = review_filtered_jobs(raw, matched, {"name": "Remote OK"})
    payload = build_review_payload(included=matched, filtered=filtered)
    assert len(payload["included"]) >= 1
    assert any(j["title"].startswith("Acme") for j in payload["included"])
    assert len(payload["filtered"]) >= 2
    reasons = {j["url"]: j.get("filter_reason", "") for j in payload["filtered"]}
    assert "principal" in reasons["https://remoteOK.com/remote-jobs/orbit-2"].lower() or (
        "excluded" in reasons["https://remoteOK.com/remote-jobs/orbit-2"].lower()
    )
    assert any(j.get("employer") == "Orbit" for j in payload["filtered"])
