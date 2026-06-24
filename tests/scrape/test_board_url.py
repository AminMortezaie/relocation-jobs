from __future__ import annotations

from relocation_jobs.scrape.board_url import resolve_generic_board_url

_SAP_URL = (
    "https://jobs.sap.com/search/?createNewAlert=false&q=&locationsearch="
    "&optionsFacetsDD_department=&optionsFacetsDD_customfield3=&optionsFacetsDD_country="
)


def test_resolve_generic_board_url_scopes_sap_to_company_country():
    company = {
        "name": "SAP",
        "careers_url": _SAP_URL,
        "locations": [
            {
                "country": "germany",
                "city": "Düsseldorf",
                "country_label": "Germany",
            },
        ],
    }
    scoped = resolve_generic_board_url(company, _SAP_URL, catalog_country="germany")
    assert "locationsearch=Germany" in scoped


def test_resolve_generic_board_url_keeps_existing_sap_locationsearch():
    company = {
        "careers_url": _SAP_URL.replace(
            "locationsearch=",
            "locationsearch=Netherlands",
        ),
    }
    url = company["careers_url"]
    assert resolve_generic_board_url(company, url, catalog_country="germany") == url


def test_resolve_generic_board_url_ignores_non_sap_urls():
    url = "https://careers.example.com/jobs"
    company = {"careers_url": url, "locations": [{"country": "germany"}]}
    assert resolve_generic_board_url(company, url, catalog_country="germany") == url
