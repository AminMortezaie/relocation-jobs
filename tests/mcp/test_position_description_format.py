from __future__ import annotations

from relocation_jobs.mcp import service


def test_get_position_description_formats_legacy_html(
    seeded_catalog_v2, mcp_documents,
):
    from relocation_jobs.catalog.repo import get_company, sync_company_board_to_catalog

    company = get_company("uk", "Acme Backend Ltd")
    jobs = list(company["matching_jobs"])
    jobs[0]["description_text"] = (
        "<h3>The Opportunity</h3><p>Build APIs with <strong>Go</strong>.</p>"
        "<ul><li>Ship reliable services</li></ul>"
    )
    company["matching_jobs"] = jobs
    sync_company_board_to_catalog("uk", company)

    detail = service.get_position_description(jobs[0]["idempotency_key"])
    assert detail.has_description is True
    assert "Build APIs" in detail.description_text
    assert "<h3>" in detail.description_html
    assert "<strong>Go</strong>" in detail.description_html
    assert "<ul>" in detail.description_html
