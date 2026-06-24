from __future__ import annotations

import re
from collections.abc import Callable

from relocation_jobs.core.ats_constants import EXCLUDE_KEYWORDS, INCLUDE_KEYWORDS
from relocation_jobs.v2.shared.predicates import any_of

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
