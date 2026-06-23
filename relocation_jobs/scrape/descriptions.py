"""HTML-to-text and visa/relocation pattern detection."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Patterns aligned with relocate.me relocation-package guide:
# https://relocate.me/international-jobs/job-search-guide/relocation-packages
VISA_RELOCATION_POSITIVE = [
    r"visa\s+sponsor",
    r"visa\s+(?:application|paperwork|support|assistance)",
    r"sponsor(?:ing)?(?:\s+\w+){0,4}\s+visas?",
    r"provide\s+visa\s+sponsor",
    r"work\s+permit\s+sponsor",
    r"immigration\s+(?:support|sponsor|assistance)",
    r"relocation\s+(?:support|package|packages|compensation|assistance|benefit|allowance|help|bonus|stipend|aid)",
    r"relocation\s+allowance",
    r"help\s+you\s+relocate",
    r"relocate\s+(?:to|you|candidates|international)",
    r"relocation\s+to\s+(?:the\s+)?\w+",
    r"provide\s+relocation",
    r"offer\s+relocation",
    r"(?:flight|airfare|air\s+fare|travel)\s+(?:ticket|cost|expense|reimbursement)",
    r"(?:temporary|short[- ]term)\s+(?:housing|accommodation|rental)",
    r"(?:accommodation|housing)\s+assistance",
    r"settling[- ]in\s+(?:support|assistance|services?)",
    r"moving\s+expenses?",
    r"sign[- ]on\s+bonus.*relocat",
    r"relocat.*sign[- ]on\s+bonus",
    r"welcome\s+applications\s+from\s+(?:talent\s+)?worldwide",
    r"international\s+(?:candidates|applicants|talent)",
]

VISA_RELOCATION_NEGATIVE = [
    r"(?:no|not|cannot|can't|unable\s+to|do\s+not|don't|does\s+not|won't|will\s+not)\s+(?:\w+\s+){0,4}(?:offer\s+)?(?:visa\s+)?sponsor",
    r"(?:no|not)\s+relocation",
    r"without\s+(?:visa\s+)?sponsor",
    r"un(?:able|fortunatel\w+)\s+to\s+(?:offer\s+)?sponsor",
    r"not\s+(?:currently\s+)?(?:able\s+to\s+)?sponsor",
    r"must\s+(?:already\s+)?(?:have|possess)\s+(?:existing\s+)?(?:the\s+)?(?:legal\s+)?right\s+to\s+work",
    r"(?:only\s+)?(?:open\s+to|candidates\s+with)\s+(?:existing\s+)?right\s+to\s+work",
    r"must\s+be\s+(?:legally\s+)?(?:eligible|authorized)\s+to\s+work",
]


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split()).lower()


def detect_visa_relocation(text: str) -> bool | None:
    """Return True/False for visa or relocation support; None if text unavailable."""
    if not text:
        return None
    normalized = text.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    if any(re.search(p, normalized) for p in VISA_RELOCATION_POSITIVE):
        return True
    if any(re.search(p, normalized) for p in VISA_RELOCATION_NEGATIVE):
        return False
    return False
