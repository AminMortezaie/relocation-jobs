"""build_companies pure helpers and mocked discovery."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from relocation_jobs.build_companies import (
    company_sort_key,
    discover_careers_static,
    discover_careers_url,
    discover_from_relocate,
    extract_link_candidates,
    fetch_html,
    load_country,
    pick_best,
    probe_common_paths,
    score_careers_url,
    size_sort_key,
    slug_from_name,
    sort_companies,
)
from tests.helpers.http_mock import MockResponse, install_requests_mock


def test_size_sort_key_variants():
    assert size_sort_key("") == 99999
    assert size_sort_key("11-50") == 11
    assert size_sort_key("501-1,000") == 501
    assert size_sort_key("10001+") == 10001
    assert size_sort_key("unknown") == 99999


def test_company_sort_key_and_sort():
    companies = [
        {"name": "Beta", "city": "Berlin, Germany", "size": "51-200"},
        {"name": "Alpha", "city": "Amsterdam", "size": "11-50"},
        {"name": "Gamma", "city": "Amsterdam", "size": "2-10"},
    ]
    sorted_names = [c["name"] for c in sort_companies(companies)]
    assert sorted_names == ["Gamma", "Alpha", "Beta"]
    key = company_sort_key(companies[0])
    assert key[0] == "berlin"


def test_slug_from_name():
    assert slug_from_name("Monzo Bank Ltd.") == "monzo-bank-ltd"
    assert slug_from_name("  Hello World  ") == "hello-world"


def test_score_careers_url():
    assert score_careers_url("https://linkedin.com/company/x") == -1
    assert score_careers_url("https://boards.greenhouse.io/acme", "Careers") >= 10
    assert score_careers_url("https://example.com/careers", "Join us") >= 5
    assert score_careers_url("https://example.com/about/team", "") < 5


def test_pick_best():
    assert pick_best([]) is None
    assert pick_best([(-1, "https://linkedin.com/x")]) is None
    assert pick_best([(5, "https://a.com/careers"), (5, "https://b.com/jobs")]).startswith("http")


def test_extract_link_candidates():
    html = """
    <html><body>
      <a href="/careers">Careers</a>
      <a href="https://boards.greenhouse.io/acme">ATS</a>
      <a href="/about">About</a>
    </body></html>
    """
    candidates = extract_link_candidates(html, "https://example.com")
    assert candidates
    urls = [u for _, u in candidates]
    assert any("greenhouse" in u for u in urls)


@pytest.mark.network
def test_fetch_html_and_probe(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={
            "example.com": MockResponse(text="<html></html>", status_code=200),
            "example.com/careers": MockResponse(text="", status_code=200),
        },
        module="relocation_jobs.build_companies",
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.requests.head",
        lambda url, **kw: MockResponse(
            status_code=200,
            url=url,
        )
        if "careers" in url
        else MockResponse(status_code=404, url=url),
    )

    html, final = fetch_html("https://example.com")
    assert html == "<html></html>"
    assert final == "https://example.com"

    found = probe_common_paths("https://example.com")
    assert isinstance(found, list)

    assert fetch_html("https://fail.example") == (None, None)


@pytest.mark.network
def test_discover_from_relocate(monkeypatch):
    relocate_html = """
    <a class="company-links__link" href="https://jobs.example.com/careers">Jobs</a>
    """
    install_requests_mock(
        monkeypatch,
        get_routes={
            "relocate.me": MockResponse(text=relocate_html, status_code=200),
        },
        module="relocation_jobs.build_companies",
    )
    url = discover_from_relocate("Example Co")
    assert url == "https://jobs.example.com/careers"


@pytest.mark.network
def test_discover_careers_static(monkeypatch):
    page = '<a href="https://boards.greenhouse.io/co/jobs">Open roles</a>'
    install_requests_mock(
        monkeypatch,
        get_routes={
            "acme.com": MockResponse(text=page, status_code=200),
        },
        module="relocation_jobs.build_companies",
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.requests.head",
        lambda url, **kw: MockResponse(status_code=404, url=url),
    )
    found = discover_careers_static("https://acme.com")
    assert found and "greenhouse" in found


@pytest.mark.network
def test_discover_careers_url_prefers_relocate(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={
            "relocate.me": MockResponse(
                text='<a class="website-link" href="https://boards.greenhouse.io/co/jobs">Jobs</a>',
                status_code=200,
            ),
        },
        module="relocation_jobs.build_companies",
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.discover_careers_static",
        lambda url: None,
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.discover_careers_playwright",
        lambda url: None,
    )
    url = discover_careers_url({"name": "Co", "careers_url": ""})
    assert "greenhouse" in url


@pytest.mark.integration
def test_load_country_wrapper(db, sample_country_data):
    from relocation_jobs.catalog_db import save_country_catalog
    from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES

    save_country_catalog("uk", sample_country_data)
    data, key = load_country("uk")
    assert COUNTRY_ARCHIVE_FILENAMES[key] == "uk_companies.json"
    assert key == "uk"
    assert data["companies"]


def test_resolve_country_key_unknown():
    with pytest.raises(SystemExit):
        load_country("not-a-country")


@pytest.mark.network
def test_discover_careers_playwright_unavailable(monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.build_companies.sync_playwright",
        lambda: (_ for _ in ()).throw(RuntimeError("playwright unavailable")),
    )
    from relocation_jobs.build_companies import discover_careers_playwright

    assert discover_careers_playwright("https://example.com") is None


@pytest.mark.network
def test_discover_careers_playwright_mocked(monkeypatch):
    mock_link = MagicMock()
    mock_link.get_attribute.return_value = "https://boards.greenhouse.io/x/jobs"
    mock_link.inner_text.return_value = "View jobs"

    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.query_selector_all.return_value = [mock_link]

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    monkeypatch.setattr(
        "relocation_jobs.build_companies.sync_playwright",
        lambda: MagicMock(__enter__=lambda s: mock_pw, __exit__=lambda *a: None),
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.probe_common_paths",
        lambda base: [(10, "https://example.com/careers")],
    )

    from relocation_jobs.build_companies import discover_careers_playwright

    result = discover_careers_playwright("https://example.com")
    assert result is not None


@pytest.mark.network
def test_discover_from_relocate_fallback_website(monkeypatch):
    relocate_html = """
    <a class="website-link" href="https://jobs.example.com">Official website</a>
    """
    install_requests_mock(
        monkeypatch,
        get_routes={"relocate.me": MockResponse(text=relocate_html, status_code=200)},
        module="relocation_jobs.build_companies",
    )
    assert discover_from_relocate("Fallback Co") == "https://jobs.example.com"


@pytest.mark.network
def test_discover_careers_url_static_fallback(monkeypatch):
    install_requests_mock(
        monkeypatch,
        get_routes={"relocate.me": MockResponse(text="", status_code=404)},
        module="relocation_jobs.build_companies",
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.discover_from_relocate",
        lambda name: None,
    )
    page = '<a href="https://example.com/careers">Jobs</a>'
    monkeypatch.setattr(
        "relocation_jobs.build_companies.discover_careers_static",
        lambda url: "https://example.com/careers" if url else None,
    )
    monkeypatch.setattr(
        "relocation_jobs.build_companies.discover_careers_playwright",
        lambda url: None,
    )
    url = discover_careers_url(
        {"name": "Co", "careers_url": "https://example.com"},
    )
    assert "careers" in url


@pytest.mark.network
def test_main_company_not_found(db, sample_country_data, monkeypatch):
    from relocation_jobs import build_companies

    monkeypatch.setattr(
        build_companies,
        "load_country",
        lambda c: (sample_country_data, "uk"),
    )
    monkeypatch.setattr(build_companies.sys, "argv", ["build_companies.py", "uk", "Missing Co"])
    with pytest.raises(SystemExit, match="not found"):
        build_companies.main()


def test_root_url():
    from relocation_jobs.build_companies import root_url

    assert root_url("example.com") == "https://example.com"
    assert root_url("https://www.example.com/path") == "https://www.example.com"


@pytest.mark.network
def test_main_sort_only(db, sample_country_data, monkeypatch, capsys):
    from relocation_jobs import build_companies

    monkeypatch.setattr(
        build_companies,
        "load_country",
        lambda c: (sample_country_data, "uk"),
    )
    saved = {}

    def fake_save(key, data):
        saved["key"] = key
        saved["data"] = data

    monkeypatch.setattr(build_companies, "save_country", fake_save)
    monkeypatch.setattr(build_companies.sys, "argv", ["build_companies.py", "uk", "--sort-only"])

    build_companies.main()
    out = capsys.readouterr().out
    assert "sort only" in out
    assert saved["key"] == "uk"


@pytest.mark.network
def test_fetch_html_request_exception(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.RequestException("fail")

    monkeypatch.setattr("relocation_jobs.build_companies.requests.get", boom)
    assert fetch_html("https://example.com") == (None, None)


@pytest.mark.network
def test_probe_common_paths_request_exception(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.RequestException("fail")

    monkeypatch.setattr("relocation_jobs.build_companies.requests.head", boom)
    assert probe_common_paths("https://example.com") == []


@pytest.mark.network
def test_discover_from_relocate_job_link_in_text(monkeypatch):
    html = '<a class="website-link" href="https://example.com">Official website</a>'
    install_requests_mock(
        monkeypatch,
        get_routes={"relocate.me": MockResponse(text=html, status_code=200)},
        module="relocation_jobs.build_companies",
    )
    assert discover_from_relocate("Text Co") == "https://example.com"


@pytest.mark.integration
def test_save_country_wrapper(db, sample_country_data, monkeypatch):
    from relocation_jobs import build_companies

    saved = {}
    monkeypatch.setattr(
        build_companies,
        "save_country_catalog_db",
        lambda key, data: saved.update({"key": key, "data": data}),
    )
    build_companies.save_country("uk", sample_country_data)
    assert saved["key"] == "uk"
    assert saved["data"]["companies"]


@pytest.mark.network
def test_main_discover_flow(db, sample_country_data, monkeypatch, capsys):
    from relocation_jobs import build_companies

    company = sample_country_data["companies"][0]
    monkeypatch.setattr(
        build_companies,
        "load_country",
        lambda c: (sample_country_data, "uk"),
    )
    monkeypatch.setattr(build_companies, "discover_careers_url", lambda c: "https://new.example/careers")
    monkeypatch.setattr(build_companies, "save_country", lambda k, d: None)
    monkeypatch.setattr(build_companies.time, "sleep", lambda s: None)
    monkeypatch.setattr(build_companies.sys, "argv", ["build_companies.py", "uk", company["name"]])

    build_companies.main()
    assert "https://new.example/careers" in capsys.readouterr().out


@pytest.mark.network
def test_main_no_args_exits(monkeypatch):
    from relocation_jobs import build_companies

    monkeypatch.setattr(build_companies.sys, "argv", ["build_companies.py"])
    with pytest.raises(SystemExit, match="Usage"):
        build_companies.main()
