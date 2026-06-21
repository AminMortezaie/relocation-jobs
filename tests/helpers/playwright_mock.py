"""Mock sync_playwright for scrape_jobs Playwright code paths."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable
from unittest.mock import MagicMock


class MockPlaywrightPage:
    def __init__(
        self,
        *,
        html: str = "",
        evaluate_results: list[Any] | None = None,
        request_urls: list[tuple[str, dict]] | None = None,
    ) -> None:
        self._html = html
        self._evaluate_results = list(evaluate_results or [])
        self._request_handlers: list[Callable] = []
        self._request_urls = request_urls or []
        self._goto_urls: list[str] = []
        self._wait_calls: list[int] = []

    def on(self, event: str, handler: Callable) -> None:
        if event == "request":
            self._request_handlers.append(handler)
            for url, headers in self._request_urls:
                req = MagicMock()
                req.url = url
                req.resource_type = "xhr"
                req.headers = headers
                handler(req)

    def goto(self, url: str, **kwargs) -> None:
        self._goto_urls.append(url)

    def content(self) -> str:
        return self._html

    def evaluate(self, script: str) -> Any:
        if self._evaluate_results:
            return self._evaluate_results.pop(0)
        return []

    def wait_for_timeout(self, ms: int) -> None:
        self._wait_calls.append(ms)

    def query_selector(self, selector: str):
        return None


class MockPlaywrightBrowser:
    def __init__(self, page: MockPlaywrightPage) -> None:
        self._page = page

    def new_context(self, **kwargs):
        ctx = MagicMock()
        ctx.new_page.return_value = self._page
        return ctx

    def new_page(self):
        return self._page

    def close(self) -> None:
        pass


class MockPlaywright:
    def __init__(self, page: MockPlaywrightPage) -> None:
        self.chromium = MagicMock()
        self.chromium.launch.return_value = MockPlaywrightBrowser(page)


@contextmanager
def mock_sync_playwright(page: MockPlaywrightPage):
    yield MockPlaywright(page)


def install_playwright_mock(
    monkeypatch,
    *,
    page: MockPlaywrightPage | None = None,
    available: bool = True,
    module: str = "relocation_jobs.scrape_jobs",
) -> MockPlaywrightPage:
    """Patch PLAYWRIGHT_AVAILABLE and sync_playwright."""
    page = page or MockPlaywrightPage()
    monkeypatch.setattr(f"{module}.PLAYWRIGHT_AVAILABLE", available)

    @contextmanager
    def _cm():
        yield MockPlaywright(page)

    monkeypatch.setattr(f"{module}.sync_playwright", _cm)
    return page
