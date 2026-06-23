"""Small scraper utilities (printing, dates)."""

from __future__ import annotations

import threading
from datetime import date

_print_lock = threading.Lock()


def safe_print(*args, **kwargs) -> None:
    with _print_lock:
        print(*args, **kwargs)


def today() -> str:
    return date.today().isoformat()
