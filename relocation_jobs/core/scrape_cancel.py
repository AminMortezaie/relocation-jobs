"""Cooperative cancellation for long-running scrape / Playwright work."""

from __future__ import annotations

from collections.abc import Callable

_cancel_checker: Callable[[], bool] | None = None


class FetchCancelled(Exception):
    """Raised when the panel (or CLI) requests scrape cancellation."""


def set_cancel_checker(checker: Callable[[], bool] | None) -> None:
    global _cancel_checker
    _cancel_checker = checker


def clear_cancel_checker() -> None:
    set_cancel_checker(None)


def is_cancel_requested() -> bool:
    return bool(_cancel_checker and _cancel_checker())


def raise_if_cancelled() -> None:
    if is_cancel_requested():
        raise FetchCancelled()
