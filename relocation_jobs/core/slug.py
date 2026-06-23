"""String helpers for company names."""

from __future__ import annotations

import re


def slug_from_name(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
