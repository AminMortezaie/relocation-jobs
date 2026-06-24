"""Cooperative cancellation for long-running scrape / Playwright work."""

from __future__ import annotations

import threading
from collections.abc import Callable

_cancel_checker: Callable[[], bool] | None = None
_thread_local = threading.local()


class FetchCancelled(Exception):
    """Raised when the panel (or CLI) requests scrape cancellation."""


def set_cancel_checker(checker: Callable[[], bool] | None) -> None:
    """Set the cancel checker for the current thread.

    Main thread also sets the global fallback so legacy code paths work.
    """
    _thread_local.cancel_checker = checker
    if threading.current_thread() is threading.main_thread():
        global _cancel_checker
        _cancel_checker = checker


def clear_cancel_checker() -> None:
    _thread_local.cancel_checker = None
    if threading.current_thread() is threading.main_thread():
        global _cancel_checker
        _cancel_checker = None


def is_cancel_requested() -> bool:
    checker = getattr(_thread_local, "cancel_checker", None) or _cancel_checker
    return bool(checker and checker())


def raise_if_cancelled() -> None:
    if is_cancel_requested():
        raise FetchCancelled()
