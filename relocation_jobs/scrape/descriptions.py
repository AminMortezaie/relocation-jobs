from __future__ import annotations

import re

from bs4 import BeautifulSoup

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


def looks_like_html(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return False
    return bool(re.search(r"<\s*(p|div|ul|ol|li|h[1-6]|span|br|img|strong|em)\b", stripped, re.I))


def html_to_readable(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "img", "iframe", "svg", "noscript"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for heading in soup.find_all(re.compile(r"^h[1-6]$", re.I)):
        heading.insert_before("\n\n")
        heading.insert_after("\n\n")
    for li in soup.find_all("li"):
        li.insert_before("• ")
        li.insert_after("\n")
    for block in soup.find_all(["p", "div", "section", "article"]):
        block.insert_after("\n\n")
    text = soup.get_text()
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


_ALLOWED_DESCRIPTION_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i", "br", "a",
}


def sanitize_job_description_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "img", "iframe", "svg", "noscript"]):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_DESCRIPTION_TAGS:
            tag.unwrap()
            continue
        if tag.name == "a":
            href = (tag.get("href") or "").strip()
            tag.attrs = {"href": href} if href.startswith(("http://", "https://")) else {}
        else:
            tag.attrs = {}
    body = soup.body or soup
    return "".join(str(child) for child in body.children).strip()


_SMARTRECRUITERS_NOISE_MARKERS = (
    "google chrome",
    "mozilla firefox",
    "i'm interested",
    "share to wechat",
)
_SMARTRECRUITERS_SECTION_RE = re.compile(
    r"\b(company description|job description|qualifications|additional information)\b",
    re.I,
)
_SMARTRECRUITERS_FOOTER_RE = re.compile(
    r"\b(by clicking the link above|privacy notice|imprint|job location)\b",
    re.I,
)
_GETYOURGUIDE_NOISE_MARKERS = (
    "life at getyourguide",
    "guiding principles",
    "how we hire",
    "tech at getyourguide",
    "open roles open roles",
    "jobs at getyourguide",
)
_ASHBY_NOISE_MARKERS = (
    "powered by ashby",
    "privacy policy",
    "cookie preferences",
    "create job alert",
    "ashbyhq.com",
)


def looks_like_smartrecruiters_page_scrape(text: str) -> bool:
    lower = (text or "").lower()
    if "smartrecruiters" not in lower:
        return False
    return sum(marker in lower for marker in _SMARTRECRUITERS_NOISE_MARKERS) >= 2


def recover_smartrecruiters_plain_text(text: str) -> str | None:
    if not looks_like_smartrecruiters_page_scrape(text):
        return None
    lower = text.lower()
    footer = _SMARTRECRUITERS_FOOTER_RE.search(lower)
    body = text[:footer.start()] if footer else text
    matches = list(_SMARTRECRUITERS_SECTION_RE.finditer(body))
    if len(matches) < 2:
        return None
    parts: list[str] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip().title()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        if not content:
            continue
        parts.append(f"<h3>{_escape_html(title)}</h3>")
        parts.append(f"<p>{_escape_html(content)}</p>")
    return "\n".join(parts) if parts else None


def looks_like_getyourguide_page_scrape(text: str) -> bool:
    lower = (text or "").lower()
    if "getyourguide" not in lower:
        return False
    return sum(marker in lower for marker in _GETYOURGUIDE_NOISE_MARKERS) >= 2


def looks_like_ashby_page_scrape(text: str) -> bool:
    lower = (text or "").lower()
    if "ashby" not in lower and "ashbyhq" not in lower:
        return False
    return sum(marker in lower for marker in _ASHBY_NOISE_MARKERS) >= 2


def needs_ashby_refetch(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if looks_like_ashby_page_scrape(stripped):
        return True
    if looks_like_html(stripped):
        return False
    return True


def needs_getyourguide_refetch(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if looks_like_getyourguide_page_scrape(stripped):
        return True
    if looks_like_html(stripped) and ("<h3>" in stripped or "<p>" in stripped):
        return False
    return True


def needs_smartrecruiters_refetch(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if looks_like_smartrecruiters_page_scrape(stripped):
        return True
    if looks_like_html(stripped) and "<h3>" in stripped:
        return False
    return True


def needs_recruitee_refetch(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if len(stripped) < 1200 and "• " not in stripped:
        return True
    return False


def format_job_description(raw: str) -> tuple[str, str]:
    stripped = (raw or "").strip()
    if not stripped:
        return "", ""
    recovered = recover_smartrecruiters_plain_text(stripped)
    if recovered:
        stripped = recovered
    if looks_like_html(stripped):
        readable = html_to_readable(stripped)
        display_html = sanitize_job_description_html(stripped)
        return readable, display_html
    paragraphs = [
        f"<p>{_escape_html(part).replace(chr(10), '<br>')}</p>"
        for part in re.split(r"\n\s*\n", stripped)
        if part.strip()
    ]
    return stripped, "".join(paragraphs)


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def detect_visa_relocation(text: str) -> bool | None:
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text.lower())
    if any(re.search(p, normalized) for p in VISA_RELOCATION_POSITIVE):
        return True
    if any(re.search(p, normalized) for p in VISA_RELOCATION_NEGATIVE):
        return False
    return False
