from __future__ import annotations

import pytest

from relocation_jobs.catalog.repo import get_company
from relocation_jobs.mcp import service


def _patch_company_enrichment(monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.companies.service.fetch_relocate_metadata",
        lambda name, country_key=None: {
            "city": "Berlin",
            "size": "51-200",
            "country": country_key or "",
        },
    )
    monkeypatch.setattr(
        "relocation_jobs.companies.service.detect_ats_for_company",
        lambda name, url, ats_hint=None: (
            "greenhouse",
            "https://boards.greenhouse.io/mcp-test-co",
        ),
    )


def test_list_supported_countries():
    items = service.list_supported_countries()
    ids = {item.id for item in items}
    assert ids == {"germany", "netherlands", "portugal", "uk"}
    assert all(item.label for item in items)


def test_list_ats_types_includes_greenhouse():
    items = service.list_ats_types()
    ids = {item.id for item in items}
    assert "greenhouse" in ids


def test_add_company_with_country_hint(db, monkeypatch):
    _patch_company_enrichment(monkeypatch)
    result = service.add_company(
        "MCP Test Co",
        "https://boards.greenhouse.io/mcp-test-co",
        country="germany",
    )
    assert result.ok is True
    assert result.country == "germany"
    assert result.name == "MCP Test Co"
    assert result.ats_type == "greenhouse"
    assert result.workspace_path == "/company/germany/mcp-test-co"
    assert result.matching_jobs_count == 0

    stored = get_company("germany", "MCP Test Co")
    assert stored is not None
    assert stored["careers_url"] == "https://boards.greenhouse.io/mcp-test-co"


def test_add_company_rejects_duplicate(db, monkeypatch):
    _patch_company_enrichment(monkeypatch)
    service.add_company(
        "MCP Dup Co",
        "https://boards.greenhouse.io/mcp-dup-co",
        country="uk",
    )
    with pytest.raises(LookupError, match="already exists"):
        service.add_company(
            "MCP Dup Co",
            "https://boards.greenhouse.io/mcp-dup-co",
            country="uk",
        )


def test_add_company_validates_required_fields():
    with pytest.raises(ValueError, match="name is required"):
        service.add_company("", "https://example.com/careers")
    with pytest.raises(ValueError, match="URL is required"):
        service.add_company("Example", "")


def test_add_company_with_custom_country(db, monkeypatch, tmp_data_dir):
    from relocation_jobs.core.location_tags import add_custom_country

    _patch_company_enrichment(monkeypatch)
    add_custom_country("Spain")
    result = service.add_company(
        "MCP Spain Co",
        "https://boards.greenhouse.io/mcp-spain-co",
        country="spain",
    )
    assert result.country == "spain"
    stored = get_company("spain", "MCP Spain Co")
    assert stored is not None


def test_add_company_parses_locations_json(db, monkeypatch):
    _patch_company_enrichment(monkeypatch)
    result = service.add_company(
        "MCP Loc Co",
        "https://boards.greenhouse.io/mcp-loc-co",
        country="uk",
        locations='[{"country": "uk", "city": "London"}]',
    )
    assert result.country == "uk"
    assert "London" in result.city
    stored = get_company("uk", "MCP Loc Co")
    assert stored is not None
    assert "London" in (stored.get("city") or "")
