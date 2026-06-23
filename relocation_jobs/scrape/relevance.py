"""Job title relevance filter for backend/software roles."""

from __future__ import annotations

import re

from relocation_jobs.core.ats_constants import EXCLUDE_KEYWORDS, INCLUDE_KEYWORDS


def is_relevant(title: str) -> bool:
    t = title.lower()
    if re.search(r"\bchief technology officer\b|\bcto\b", t):
        return False
    has_include = any(kw in t for kw in INCLUDE_KEYWORDS)
    if not has_include:
        return False

    # "Marketing" etc. often labels the team, not the role (e.g. Fullstack Engineer – Marketing).
    if re.search(r"\b(engineer|developer|programmer)\b", t):
        excludes = [kw for kw in EXCLUDE_KEYWORDS if kw.strip() != "marketing"]
    else:
        excludes = EXCLUDE_KEYWORDS

    if any(kw in t for kw in excludes):
        return False
    # "Senior/Staff Product Engineer" is a level range, not a Staff-only role.
    if re.search(r"\bstaff\b", t) and not re.search(r"senior\s*/\s*staff", t):
        return False
    if "cloud engineer" in t and "backend" not in t and "software" not in t:
        return False
    if "ai platform" in t and "backend" not in t and "software" not in t:
        return False
    return True


def explain_title_filter(title: str) -> str:
    """Human-readable reason when ``is_relevant`` rejects a title."""
    t = (title or "").lower()
    if re.search(r"\bchief technology officer\b|\bcto\b", t):
        return "Title excluded (CTO)"
    if not any(kw in t for kw in INCLUDE_KEYWORDS):
        return "Title not relevant (no backend/software keyword)"
    if re.search(r"\b(engineer|developer|programmer)\b", t):
        excludes = [kw for kw in EXCLUDE_KEYWORDS if kw.strip() != "marketing"]
    else:
        excludes = EXCLUDE_KEYWORDS
    for kw in excludes:
        if kw in t:
            label = kw.strip() or kw
            return f"Title excluded ({label})"
    if re.search(r"\bstaff\b", t) and not re.search(r"senior\s*/\s*staff", t):
        return "Title excluded (staff level)"
    if "cloud engineer" in t and "backend" not in t and "software" not in t:
        return "Title excluded (cloud engineer without backend/software)"
    if "ai platform" in t and "backend" not in t and "software" not in t:
        return "Title excluded (AI platform without backend/software)"
    return "Title not relevant"
