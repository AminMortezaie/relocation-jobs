from __future__ import annotations

import re
from collections.abc import Callable

from relocation_jobs.core.ats_constants import EXCLUDE_KEYWORDS, INCLUDE_KEYWORDS
from relocation_jobs.shared.predicates import any_of

_IRRELEVANT_TITLE_RULES: tuple[Callable[[tuple[str, list[str]]], bool], ...] = (
    lambda ctx: bool(re.search(r"\bchief technology officer\b|\bcto\b", ctx[0])),
    lambda ctx: any(kw in ctx[0] for kw in ctx[1]),
    lambda ctx: bool(re.search(r"\bstaff\b", ctx[0])) and not re.search(
        r"senior\s*/\s*staff", ctx[0],
    ),
    lambda ctx: "cloud engineer" in ctx[0] and "backend" not in ctx[0] and "software" not in ctx[0],
    lambda ctx: "ai platform" in ctx[0] and "backend" not in ctx[0] and "software" not in ctx[0],
)


def is_relevant(title: str) -> bool:
    t = title.lower()
    if not any(kw in t for kw in INCLUDE_KEYWORDS):
        return False
    if re.search(r"\b(engineer|developer|programmer)\b", t):
        excludes = [kw for kw in EXCLUDE_KEYWORDS if kw.strip() != "marketing"]
    else:
        excludes = EXCLUDE_KEYWORDS
    ctx = (t, excludes)
    return not any_of(ctx, _IRRELEVANT_TITLE_RULES)


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
            return f"Title excluded ({kw.strip() or kw})"
    if re.search(r"\bstaff\b", t) and not re.search(r"senior\s*/\s*staff", t):
        return "Title excluded (staff level)"
    if "cloud engineer" in t and "backend" not in t and "software" not in t:
        return "Title excluded (cloud engineer without backend/software)"
    if "ai platform" in t and "backend" not in t and "software" not in t:
        return "Title excluded (AI platform without backend/software)"
    return "Title not relevant"
