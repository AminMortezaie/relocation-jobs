"""In-memory country catalog read cache."""

from __future__ import annotations

import re
import threading
from pathlib import Path

_country_cache: dict[str, dict | None] = {}
_country_cache_lock = threading.Lock()


def invalidate_country_cache(country_key: str | None = None) -> None:
    """Drop cached catalog reads after writes (country_key=None clears all)."""
    with _country_cache_lock:
        if country_key is None:
            _country_cache.clear()
        else:
            _country_cache.pop(country_key, None)


def country_key_from_filename(name: str) -> str | None:
    m = re.match(r"(\w+)_companies\.json", Path(name).name)
    return m.group(1) if m else None
