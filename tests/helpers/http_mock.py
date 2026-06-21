"""Reusable helpers for mocking requests.get/post in scrape_jobs tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

FIXTURES_ATS = Path(__file__).resolve().parent.parent / "fixtures" / "ats"


class MockResponse:
    """Minimal requests.Response stand-in."""

    def __init__(
        self,
        *,
        text: str = "",
        json_data: Any = None,
        status_code: int = 200,
        content: bytes | None = None,
        ok: bool | None = None,
        url: str = "",
    ) -> None:
        self.text = text
        self.status_code = status_code
        self.ok = ok if ok is not None else status_code < 400
        self._json_data = json_data
        self.content = content if content is not None else text.encode("utf-8")
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        if self._json_data is not None:
            return self._json_data
        return json.loads(self.text)


def load_ats_fixture(name: str) -> Any:
    """Load JSON/XML fixture from tests/fixtures/ats/."""
    path = FIXTURES_ATS / name
    text = path.read_text(encoding="utf-8")
    if name.endswith(".json"):
        return json.loads(text)
    return text


def _match_route(url: str, route_key: str) -> bool:
    return route_key in url


def install_requests_mock(
    monkeypatch,
    *,
    get_routes: dict[str, MockResponse | Callable[..., MockResponse]] | None = None,
    post_routes: dict[str, MockResponse | Callable[..., MockResponse]] | None = None,
    default_get: MockResponse | None = None,
    default_post: MockResponse | None = None,
    module: str = "relocation_jobs.scrape_jobs",
) -> dict[str, list]:
    """Patch requests.get/post; route keys are URL substrings."""
    get_routes = get_routes or {}
    post_routes = post_routes or {}
    calls: dict[str, list] = {"get": [], "post": []}

    def _resolve(route_map, url, kwargs, fallback):
        for key, factory in route_map.items():
            if _match_route(url, key):
                if callable(factory):
                    return factory(url=url, **kwargs)
                return factory
        if fallback is not None:
            return fallback
        return MockResponse(status_code=404, text="not found")

    def fake_get(url, *args, **kwargs):
        calls["get"].append((url, kwargs))
        response = _resolve(get_routes, url, kwargs, default_get)
        if not getattr(response, "url", ""):
            response.url = url
        return response

    def fake_post(url, *args, **kwargs):
        calls["post"].append((url, kwargs))
        return _resolve(post_routes, url, kwargs, default_post)

    monkeypatch.setattr(f"{module}.requests.get", fake_get)
    monkeypatch.setattr(f"{module}.requests.post", fake_post)
    return calls


def json_response(data: Any, *, status_code: int = 200) -> MockResponse:
    return MockResponse(json_data=data, status_code=status_code)


def text_response(text: str, *, status_code: int = 200) -> MockResponse:
    return MockResponse(text=text, status_code=status_code)


def magic_json_response(data: Any, *, status_code: int = 200) -> MagicMock:
    """MagicMock variant matching existing test style."""
    response = MagicMock()
    response.status_code = status_code
    response.ok = status_code < 400
    response.text = json.dumps(data) if not isinstance(data, str) else data
    response.content = response.text.encode("utf-8")
    response.raise_for_status = MagicMock()
    response.json.return_value = data
    return response
