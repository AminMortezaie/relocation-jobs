from __future__ import annotations

import threading

from relocation_jobs.core.location_tags import invalidate_country_labels_cache

_country_cache: dict[str, dict | None] = {}
_country_cache_lock = threading.Lock()


def invalidate_country_cache(country_key: str | None = None) -> None:
    invalidate_country_labels_cache()
    with _country_cache_lock:
        if country_key is None:
            _country_cache.clear()
        else:
            _country_cache.pop(country_key, None)
