"""ATS type and board URL detection (static HTML, URL patterns, Playwright).

Shared by scrape_jobs and company_service — neither should duplicate this logic.
"""

from __future__ import annotations

import json
import re
import threading
from urllib.parse import urljoin, urlparse

import requests

from relocation_jobs.core.scrape_cancel import FetchCancelled, raise_if_cancelled
from relocation_jobs.core.slug import slug_from_name

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_playwright_sem = threading.Semaphore(2)


def _playwright_browser_context(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="en-US")
    return browser, context


def _playwright_pause(page, total_ms: int = 3500, step_ms: int = 200) -> None:
    """Sleep in short chunks so cancellation can interrupt Playwright waits."""
    elapsed = 0
    while elapsed < total_ms:
        raise_if_cancelled()
        chunk = min(step_ms, total_ms - elapsed)
        page.wait_for_timeout(chunk)
        elapsed += chunk


# ── ATS API patterns for XHR interception ────────────────────────────────────
# Each entry: (regex matching an intercepted request URL, ats_type, fn to extract ats_url)

def _extract_personio(url: str) -> str:
    m = re.search(r"(https?://[a-z0-9-]+\.(?:jobs\.personio\.(?:de|com)|app\.personio\.com))", url)
    return m.group(1) if m else url

def _extract_lever(url: str) -> str:
    m = re.search(r"https?://(?:jobs\.eu\.lever\.co|jobs\.lever\.co|api(?:\.eu)?\.lever\.co)/v0/postings/([a-z0-9-]+)", url)
    if m:
        host = "jobs.eu.lever.co" if "eu" in url else "jobs.lever.co"
        return f"https://{host}/{m.group(1)}"
    return url

def _extract_greenhouse(url: str) -> str:
    # Handle embed JS/HTML: greenhouse.io/embed/...?for=slug
    m_embed = re.search(r"greenhouse\.io/embed[^?]*\?(?:[^&]*&)*for=([a-z0-9_-]+)", url)
    if m_embed:
        return f"https://boards.greenhouse.io/{m_embed.group(1)}"
    m = re.search(r"boards(?:-api)?\.(?:eu\.)?greenhouse\.io/(?:v1/boards/)?([a-z0-9_-]+)", url)
    slug = m.group(1) if m else ""
    if slug in ("embed", "job_board", "jobs", ""):
        return url  # could not extract real slug
    return f"https://boards.greenhouse.io/{slug}"

def _extract_greenhouse_eu(url: str) -> str:
    # Handle embed: boards.eu.greenhouse.io/embed/job_board/js?for=slug
    m_embed = re.search(r"greenhouse\.io/embed[^?]*\?(?:[^&]*&)*for=([a-z0-9_-]+)", url)
    if m_embed:
        return f"https://boards.eu.greenhouse.io/{m_embed.group(1)}"
    m = re.search(r"boards(?:-api)?\.eu\.greenhouse\.io/(?:v1/boards/)?([a-z0-9_-]+)", url)
    slug = m.group(1) if m else ""
    if slug in ("embed", "job_board", "jobs", ""):
        return url
    return f"https://boards.eu.greenhouse.io/{slug}"

def _extract_ashby(url: str) -> str:
    m = re.search(r"api\.ashbyhq\.com/posting-api/job-board/([a-z0-9._-]+)", url)
    if m:
        return f"https://jobs.ashbyhq.com/{m.group(1)}"
    m2 = re.search(r"jobs\.ashbyhq\.com/([a-z0-9._-]+)", url)
    return f"https://jobs.ashbyhq.com/{m2.group(1)}" if m2 else url

def _extract_workable(url: str) -> str:
    m = re.search(r"apply\.workable\.com/(?:api/v\d+/accounts/)?([a-z0-9-]+)", url)
    return f"https://apply.workable.com/{m.group(1)}/" if m else url

def _extract_recruitee(url: str) -> str:
    m = re.search(r"([a-z0-9-]+)\.recruitee\.com", url)
    if not m:
        return url
    slug = m.group(1)
    # careers-analytics is a tracking proxy — not the real company slug
    if slug in ("careers-analytics", "careers"):
        return url  # signal caller to dig deeper
    return f"https://{slug}.recruitee.com/"

def _smartrecruiters_company_id(ats_url: str) -> str:
    url = (ats_url or "").split("?")[0].rstrip("/")
    for pattern in (
        r"api\.smartrecruiters\.com/v1/companies/([A-Za-z0-9_-]+)",
        r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)",
        r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)",
    ):
        m = re.search(pattern, url, re.I)
        if m:
            return m.group(1)
    slug = url.split("/")[-1]
    return slug if slug and slug.lower() != "postings" else ""


def _smartrecruiters_api_url(company_id: str) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"


def _extract_smartrecruiters(url: str) -> str:
    company_id = _smartrecruiters_company_id(url)
    return _smartrecruiters_api_url(company_id) if company_id else url

def _extract_teamtailor(url: str, headers: dict) -> tuple[str, str]:
    auth = headers.get("authorization", "")
    m_token = re.search(r"token=(\S+)", auth)
    m_key_url = re.search(r"api_key=([^&\s]+)", url)
    key = m_token.group(1) if m_token else (m_key_url.group(1) if m_key_url else "")
    return "teamtailor", key  # key is stored in ats_url for teamtailor


_WORKDAY_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$", re.I)
_META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv\s*=\s*["\']?refresh["\']?[^>]*content\s*=\s*["\'][^"\']*?\burl\s*=\s*([^"\'>\s;]+)',
    re.I,
)
_WORKDAY_BOARD_URL_RE = re.compile(
    r"(https?://[a-z0-9.-]*myworkday(?:jobs|site)\.com"
    r"(?:/[a-z]{2}-[A-Z]{2})?/[A-Za-z0-9][A-Za-z0-9_-]+(?:/[A-Za-z0-9][A-Za-z0-9_-]+)?)",
    re.I,
)


def _workday_board_base(
    host: str,
    tenant: str,
    site: str,
    locale: str = "en-US",
) -> str:
    host = host.removeprefix("https://").removeprefix("http://")
    if "myworkdaysite" in host:
        return f"https://{host}/{locale}/{tenant}/{site}"
    return f"https://{host}/{locale}/{site}"


def _parse_workday_board_url(
    host: str,
    path_parts: list[str],
) -> tuple[str, str, str] | None:
    """Return (tenant, site, locale) from a Workday careers board URL."""
    host_l = (host or "").lower()
    if "myworkdayjobs.com" not in host_l and "myworkdaysite.com" not in host_l:
        return None
    subdomain = host_l.split(".")[0]
    parts = [p for p in path_parts if p]
    if not parts:
        return None
    locale = "en-US"
    if _WORKDAY_LOCALE_RE.match(parts[0]):
        locale = parts[0]
        parts = parts[1:]
    if not parts:
        return None
    if "myworkdaysite" in host_l and subdomain == "wd3":
        if len(parts) < 2:
            return None
        return parts[0], parts[1], locale
    return subdomain, parts[0], locale


def _workday_api_and_base(api_url: str) -> tuple[str, str]:
    api = (api_url or "").split("|")[0].split("?")[0].rstrip("/")
    if "|" in (api_url or ""):
        return api, (api_url or "").split("|", 1)[1].strip()
    m = re.match(r"(https://[^/]+)/wday/cxs/([^/]+)/([^/]+)/jobs", api)
    if not m:
        return api, ""
    host, tenant, site = m.group(1), m.group(2), m.group(3)
    return api, _workday_board_base(host, tenant, site)


def _workday_url_from_html_match(m: re.Match) -> str | None:
    return _detect_workday_from_url(m.group(1))[1]


def _accept_html_ats_match(ats_type: str, slug_or_url: str | None) -> bool:
    if not slug_or_url:
        return False
    if ats_type == "workday":
        return "|" in slug_or_url and "/wday/cxs/" in slug_or_url
    return slug_or_url.rstrip("/").split("/")[-1] not in ("embed", "jobs", "")


def _scan_html_for_ats(html: str) -> tuple[str | None, str | None]:
    for pattern, ats_type, builder in HTML_ATS_PATTERNS:
        m = re.search(pattern, html)
        if m:
            slug_or_url = builder(m)
            if _accept_html_ats_match(ats_type, slug_or_url):
                return ats_type, slug_or_url
    return None, None


def _follow_meta_refresh(html: str, page_url: str) -> str | None:
    m = _META_REFRESH_RE.search(html)
    if not m:
        return None
    target = urljoin(page_url, m.group(1).strip())
    if target.rstrip("/") == page_url.rstrip("/"):
        return None
    return target


def _extract_workday(url: str) -> str:
    api = url.split("?")[0]
    _, base = _workday_api_and_base(api)
    return f"{api}|{base}" if base else api


XHR_ATS_PATTERNS = [
    # (url_regex, ats_type, extractor_fn)
    (r"personio\.com/api/careers/jobs",              "personio",
     lambda url: "https://www.personio.com/api/careers/jobs/list"),
    (r"\.jobs\.personio\.|\.app\.personio\.com",     "personio",        _extract_personio),
    (r"api(?:\.eu)?\.lever\.co/v0/postings/",        "lever",           _extract_lever),
    (r"jobs\.eu\.lever\.co/",                        "lever_eu",        _extract_lever),
    (r"boards(?:-api)?\.eu\.greenhouse\.io",         "greenhouse_eu",   _extract_greenhouse_eu),
    (r"boards(?:-api)?\.greenhouse\.io",             "greenhouse",      _extract_greenhouse),
    (r"api\.ashbyhq\.com/posting-api/",              "ashby",           _extract_ashby),
    (r"apply\.workable\.com/api/",                   "workable",        _extract_workable),
    (r"\.recruitee\.com/api/",                       "recruitee",       _extract_recruitee),
    (r"api\.smartrecruiters\.com/v1/companies/",     "smartrecruiters", _extract_smartrecruiters),
    (r"api\.teamtailor\.com/v1/jobs",                "teamtailor",      None),
    (r"join\.com/api/public/companies/\d+/jobs",     "join",
     lambda url: _detect_join_from_url(url)[1] or url),
    (r"api-prod\.letsdeel\.com",                     "deel",
     lambda url: _detect_deel_from_url(url)[1] or url),
    (r"/wday/cxs/[^/]+/[^/]+/jobs",                 "workday",         _extract_workday),
]

# Static HTML patterns as a secondary check (for pages that load ATS links in HTML
# before JS executes the actual API calls)
HTML_ATS_PATTERNS = [
    (r"personio\.com/api/careers/jobs/list",         "personio",
     lambda m: "https://www.personio.com/api/careers/jobs/list"),
    (r"([a-z0-9-]+)\.jobs\.personio\.(de|com)",      "personio",
     lambda m: f"https://{m.group(1)}.jobs.personio.{m.group(2)}/"),
    (r"jobs\.eu\.lever\.co/([a-z0-9-]+)",            "lever_eu",
     lambda m: f"https://jobs.eu.lever.co/{m.group(1)}"),
    (r"jobs\.lever\.co/([a-z0-9-]+)",                "lever",
     lambda m: f"https://jobs.lever.co/{m.group(1)}"),
    (r"boards-api\.greenhouse\.io/v1/boards/([a-z0-9_-]+)", "greenhouse",
     lambda m: f"https://boards.greenhouse.io/{m.group(1)}"),
    (r"job-boards\.greenhouse\.io/([a-z0-9_-]+)",    "greenhouse",
     lambda m: f"https://boards.greenhouse.io/{m.group(1)}"),
    (r"boards\.eu\.greenhouse\.io/([a-z0-9_-]+)",    "greenhouse_eu",
     lambda m: f"https://boards.eu.greenhouse.io/{m.group(1)}"),
    (r"boards\.greenhouse\.io/([a-z0-9_-]+)",        "greenhouse",
     lambda m: f"https://boards.greenhouse.io/{m.group(1)}"),
    (r"([a-z0-9-]+)\.recruitee\.com/",              "recruitee",
     lambda m: f"https://{m.group(1)}.recruitee.com/"),
    (r"apply\.workable\.com/([a-z0-9-]+)/",          "workable",
     lambda m: f"https://apply.workable.com/{m.group(1)}/"),
    (r"jobs\.ashbyhq\.com/([a-z0-9._-]+)",           "ashby",
     lambda m: f"https://jobs.ashbyhq.com/{m.group(1)}"),
    (r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)", "smartrecruiters",
     lambda m: _smartrecruiters_api_url(m.group(1))),
    (r"(?:teamtailor-cdn\.com|([a-z0-9-]+)\.teamtailor\.com)", "teamtailor",
     lambda m: (
         f"https://{m.group(1)}.teamtailor.com/jobs"
         if m.group(1) and m.group(1).lower() not in ("www", "api", "careers", "app")
         else None
     )),
    (r"join\.com/companies/([a-zA-Z0-9_-]+)",          "join",
     lambda m: f"https://join.com/companies/{m.group(1)}"),
    (r"jobs\.deel\.com/([a-zA-Z0-9_-]+)",             "deel",
     lambda m: f"https://jobs.deel.com/{m.group(1)}"),
    (_WORKDAY_BOARD_URL_RE.pattern,                  "workday",
     _workday_url_from_html_match),
]
def _detect_deel_from_url(careers_url: str) -> tuple[str | None, str | None]:
    """Deel ATS boards live at jobs.deel.com/{slug} (optional location filters in query)."""
    m = re.search(r"jobs\.deel\.com/([a-zA-Z0-9_-]+)", careers_url, re.I)
    if not m:
        return None, None
    slug = m.group(1).lower()
    if slug in ("embed", "jobs", "job-details"):
        return None, None
    parsed = urlparse(careers_url)
    board = f"https://jobs.deel.com/{m.group(1)}"
    if parsed.query:
        board = f"{board}?{parsed.query}"
    return "deel", board


def _detect_join_from_url(careers_url: str) -> tuple[str | None, str | None]:
    """join.com hosts company boards at /companies/{slug}."""
    m = re.search(r"join\.com/companies/([a-zA-Z0-9_-]+)/?", careers_url, re.I)
    if not m:
        return None, None
    slug = m.group(1)
    if slug.lower() in ("embed", "jobs"):
        return None, None
    return "join", f"https://join.com/companies/{slug}"


def _detect_applytojob_from_url(careers_url: str) -> tuple[str | None, str | None]:
    if re.search(r"\.applytojob\.com/?", careers_url, re.I):
        base = careers_url.split("?", 1)[0].rstrip("/") + "/"
        return "applytojob", base
    return None, None


def _detect_bamboohr_from_url(careers_url: str) -> tuple[str | None, str | None]:
    m = re.search(r"https?://([a-z0-9-]+)\.bamboohr\.com/careers", careers_url, re.I)
    if m:
        sub = m.group(1)
        return "bamboohr", f"https://{sub}.bamboohr.com/careers/list"
    return None, None

def _detect_job_shop_from_url(careers_url: str) -> tuple[str | None, str | None]:
    """Talents Connect boards embed api.my-job-shop.com in the careers page."""
    if not careers_url:
        return None, None
    page_url = careers_url.split("#", 1)[0].strip()
    if not page_url:
        return None, None
    if "/search" not in page_url:
        page_url = page_url.rstrip("/") + "/search"
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return None, None
    if "api.my-job-shop.com" not in r.text and "job-shop.com" not in r.text:
        return None, None
    if not _parse_job_shop_config(r.text, careers_url):
        return None, None
    base = careers_url.split("#", 1)[0].rstrip("/") + "/"
    return "job_shop", base
def _detect_smartrecruiters_from_careers_url(
    careers_url: str,
) -> tuple[str | None, str | None]:
    for pattern in (
        r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)",
        r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)",
    ):
        m = re.search(pattern, careers_url or "", re.I)
        if m:
            return "smartrecruiters", _smartrecruiters_api_url(m.group(1))
    return None, None


def _detect_smartrecruiters_from_redcare_careers(
    careers_url: str,
) -> tuple[str | None, str | None]:
    if "redcare-pharmacy.com" not in (careers_url or ""):
        return None, None
    try:
        r = requests.get(
            "https://www.redcare-pharmacy.com/api/get-job-posting",
            params={"loadAll": "true"},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("items") or []
        for item in items:
            ref = item.get("ref") or ""
            m = re.search(
                r"api\.smartrecruiters\.com/v1/companies/([A-Za-z0-9_-]+)/",
                ref,
                re.I,
            )
            if m:
                return "smartrecruiters", _smartrecruiters_api_url(m.group(1))
            identifier = (item.get("company") or {}).get("identifier") or ""
            if identifier:
                return "smartrecruiters", _smartrecruiters_api_url(identifier)
    except Exception:
        pass
    return None, None


def _detect_recruitee_from_careers_host(careers_url: str) -> tuple[str | None, str | None]:
    """careers.{slug}.com / careers.{slug}.io often maps to {slug}.recruitee.com."""
    parsed = urlparse(careers_url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(".smartrecruiters.com") or host == "smartrecruiters.com":
        return None, None
    m = re.match(r"careers\.([a-z0-9-]+)\.(com|io|co|eu)$", host)
    if not m:
        return None, None
    slug = m.group(1)
    if slug in ("www", "jobs", "apply"):
        return None, None
    return "recruitee", f"https://{slug}.recruitee.com/"


def _detect_recruitee_board_url(careers_url: str) -> tuple[str | None, str | None]:
    m = re.search(r"https?://([a-z0-9-]+)\.recruitee\.com", careers_url, re.I)
    if not m:
        return None, None
    slug = m.group(1).lower()
    if slug in ("www", "api", "careers", "app"):
        return None, None
    return "recruitee", f"https://{slug}.recruitee.com/"


def _detect_teamtailor_from_url(careers_url: str) -> tuple[str | None, str | None]:
    """boards at {company}.teamtailor.com/jobs"""
    m = re.search(r"https?://([a-z0-9-]+)\.teamtailor\.com", careers_url, re.I)
    if not m:
        return None, None
    slug = m.group(1).lower()
    if slug in ("www", "api", "careers", "app"):
        return None, None
    return "teamtailor", f"https://{slug}.teamtailor.com/jobs"


def _detect_workday_from_url(careers_url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(careers_url.split("?")[0])
    host = (parsed.hostname or "").lower()
    if "myworkdayjobs.com" not in host and "myworkdaysite.com" not in host:
        return None, None
    path_parts = [p for p in parsed.path.split("/") if p]
    if not path_parts:
        return None, None
    if path_parts[:2] == ["wday", "cxs"] and len(path_parts) >= 5 and path_parts[-1] == "jobs":
        tenant, site = path_parts[2], path_parts[3]
        api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        base = _workday_api_and_base(api)[1]
        if not base:
            return None, None
        return "workday", f"{api}|{base}"
    board = _parse_workday_board_url(host, path_parts)
    if not board:
        return None, None
    tenant, site, locale = board
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    base = _workday_board_base(host, tenant, site, locale)
    return "workday", f"{api}|{base}"


def _detect_hirehive_from_url(careers_url: str) -> tuple[str | None, str | None]:
    m = re.search(r"https?://([a-z0-9-]+)\.hirehive\.com", careers_url, re.I)
    if not m:
        return None, None
    return "hirehive", f"https://{m.group(1)}.hirehive.com"

def _detect_ats_from_careers_url(careers_url: str) -> tuple[str | None, str | None]:
    for detector in (
        _detect_smartrecruiters_from_careers_url,
        _detect_smartrecruiters_from_redcare_careers,
        _detect_workday_from_url,
        _detect_hirehive_from_url,
        _detect_teamtailor_from_url,
        _detect_deel_from_url,
        _detect_join_from_url,
        _detect_applytojob_from_url,
        _detect_bamboohr_from_url,
        _detect_recruitee_board_url,
        _detect_recruitee_from_careers_host,
    ):
        detected = detector(careers_url)
        if detected[0]:
            return detected
    return None, None
# ── ATS auto-detection via Playwright ────────────────────────────────────────

def detect_ats_via_playwright(
    careers_url: str,
    *,
    ats_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Load the careers page in a headless browser, intercept all XHR/fetch calls,
    and match against known ATS patterns.
    Returns (ats_type, ats_url) or (None, None).
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None, None

    found_ats: list[tuple[str, str]] = []

    def on_request(req):
        if req.resource_type not in ("xhr", "fetch", "script", "document"):
            return
        url = req.url
        hdrs = dict(req.headers)
        for pattern, ats_type, extractor in XHR_ATS_PATTERNS:
            if re.search(pattern, url, re.I):
                if ats_type == "teamtailor":
                    _, key = _extract_teamtailor(url, hdrs)
                    found_ats.append(("teamtailor", key or url))
                else:
                    found_ats.append((ats_type, extractor(url)))
                return

    try:
        raise_if_cancelled()
        with _playwright_sem:
            with sync_playwright() as p:
                browser, context = _playwright_browser_context(p)
                page = context.new_page()
                page.on("request", on_request)
                page.goto(careers_url, wait_until="domcontentloaded", timeout=25000)
                _playwright_pause(page, 3500)

                # If XHR interception found nothing, try parsing the rendered HTML
                if not found_ats:
                    raise_if_cancelled()
                    html = page.content()
                    hint = (ats_hint or "").strip().lower()
                    html_match = _scan_html_for_ats(html)
                    if html_match[0]:
                        if not hint or html_match[0] == hint:
                            found_ats.append(html_match)

                browser.close()
    except FetchCancelled:
        raise
    except Exception as e:
        print(f"    Playwright detection error: {e}")

    if found_ats:
        if ats_hint:
            hint = ats_hint.strip().lower()
            for ats_type, ats_url in found_ats:
                if ats_type == hint and ats_url:
                    return ats_type, ats_url
            return None, None
        return found_ats[0]
    return None, None


def detect_ats_static(careers_url: str, *, _depth: int = 0) -> tuple[str | None, str | None]:
    """Fast static HTML fetch — no JS, no Playwright."""
    url_detected = _detect_ats_from_careers_url(careers_url)
    if url_detected[0]:
        return url_detected

    try:
        r = requests.get(
            careers_url,
            headers=HEADERS,
            timeout=12,
            allow_redirects=True,
        )
        html = r.text
        page_url = getattr(r, "url", None) or careers_url
    except Exception:
        return None, None

    found = _scan_html_for_ats(html)
    if found[0]:
        return found

    if _depth < 2:
        refresh_target = _follow_meta_refresh(html, page_url)
        if refresh_target:
            return detect_ats_static(refresh_target, _depth=_depth + 1)

    return None, None


ATS_HINT_URL_DETECTORS = (
    _detect_smartrecruiters_from_careers_url,
    _detect_smartrecruiters_from_redcare_careers,
    _detect_workday_from_url,
    _detect_hirehive_from_url,
    _detect_teamtailor_from_url,
    _detect_deel_from_url,
    _detect_join_from_url,
    _detect_applytojob_from_url,
    _detect_bamboohr_from_url,
    _detect_recruitee_board_url,
    _detect_recruitee_from_careers_host,
    _detect_job_shop_from_url,
)

_CAREERS_PAGE_AS_ATS = frozenset({
    "atlassian",
    "bol",
    "epam",
    "jibe",
    "movingimage",
    "project_a",
    "rss",
})


def _company_slug(name: str) -> str:
    slug = slug_from_name(name or "")
    if slug:
        return slug
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def guess_ats_url_from_name(ats_type: str, company_name: str) -> str:
    slug = _company_slug(company_name)
    if not slug:
        return ""
    builders: dict[str, object] = {
        "recruitee": lambda s: f"https://{s}.recruitee.com/",
        "greenhouse": lambda s: f"https://boards.greenhouse.io/{s}",
        "greenhouse_eu": lambda s: f"https://boards.eu.greenhouse.io/{s}",
        "ashby": lambda s: f"https://jobs.ashbyhq.com/{s}",
        "workable": lambda s: f"https://apply.workable.com/{s}/",
        "lever": lambda s: f"https://jobs.lever.co/{s}",
        "lever_eu": lambda s: f"https://jobs.eu.lever.co/{s}",
        "personio": lambda s: f"https://{s}.jobs.personio.de/",
        "smartrecruiters": lambda s: _smartrecruiters_api_url(s),
        "join": lambda s: f"https://join.com/companies/{s}",
        "deel": lambda s: f"https://jobs.deel.com/{s}",
        "teamtailor": lambda s: f"https://{s}.teamtailor.com/jobs",
        "applytojob": lambda s: f"https://{s}.applytojob.com/",
        "bamboohr": lambda s: f"https://{s}.bamboohr.com/careers/list",
        "hirehive": lambda s: f"https://{s}.hirehive.com",
    }
    builder = builders.get(ats_type)
    return builder(slug) if builder else ""


def _detect_ats_in_html_for_hint(
    careers_url: str,
    ats_hint: str,
) -> tuple[str | None, str | None]:
    try:
        r = requests.get(careers_url, headers=HEADERS, timeout=12)
        html = r.text
    except Exception:
        return None, None

    for pattern, ats_type, builder in HTML_ATS_PATTERNS:
        if ats_type != ats_hint:
            continue
        m = re.search(pattern, html)
        if not m:
            continue
        slug_or_url = builder(m)
        if slug_or_url and slug_or_url.rstrip("/").split("/")[-1] not in ("embed", "jobs", ""):
            return ats_type, slug_or_url
    return None, None


def detect_ats_for_hint(
    company_name: str,
    careers_url: str,
    ats_hint: str,
) -> tuple[str, str]:
    """
    Resolve ATS type + board URL when the user picked an ATS in the add-company form.
    Falls back to slug guesses and finally stores the hint with an empty board URL.
    """
    hint = (ats_hint or "").strip().lower()
    if not hint or hint == "auto":
        return "", ""

    for detector in ATS_HINT_URL_DETECTORS:
        detected = detector(careers_url)
        if detected[0] == hint and detected[1]:
            return detected

    static_match = _detect_ats_in_html_for_hint(careers_url, hint)
    if static_match[0] and static_match[1]:
        return static_match

    if detect_ats_via_playwright:
        playwright_match = detect_ats_via_playwright(careers_url, ats_hint=hint)
        if playwright_match[0] and playwright_match[1]:
            return playwright_match

    if hint in _CAREERS_PAGE_AS_ATS and careers_url:
        return hint, careers_url.rstrip("/") + "/"

    guessed = guess_ats_url_from_name(hint, company_name)
    if guessed:
        return hint, guessed

    return hint, ""

def _resolve_nuxt_payload_node(data: list, idx, resolving: set | None = None):
    if resolving is None:
        resolving = set()
    if idx in resolving:
        return None
    if not isinstance(idx, int) or idx < 0 or idx >= len(data):
        return idx
    resolving.add(idx)
    val = data[idx]
    if isinstance(val, list) and len(val) >= 2 and val[0] in ("ShallowReactive", "Reactive"):
        return _resolve_nuxt_payload_node(data, val[1], resolving)
    if (
        isinstance(val, list)
        and len(val) >= 3
        and isinstance(val[0], str)
        and val[0] == ""
    ):
        out = {}
        for pos in range(1, len(val) - 1, 2):
            key = _resolve_nuxt_payload_node(data, val[pos], resolving)
            item = _resolve_nuxt_payload_node(data, val[pos + 1], resolving)
            if isinstance(key, str):
                out[key] = item
        return out
    if isinstance(val, list):
        return [_resolve_nuxt_payload_node(data, item, resolving) for item in val]
    return val


def _resolve_nuxt_scalar(data: list, value):
    if isinstance(value, int):
        resolved = _resolve_nuxt_payload_node(data, value, set())
        if isinstance(resolved, int):
            return _resolve_nuxt_scalar(data, resolved)
        return resolved
    return value


def _parse_job_shop_config(html: str, careers_url: str) -> tuple[str, str, str] | None:
    """Return (typesense_api_key, tenant_id, backoffice_vanity) from a Job Shop page."""
    match = re.search(
        r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.S,
    )
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
        root = _resolve_nuxt_payload_node(payload, 1)
        store = _resolve_nuxt_scalar(payload, root.get("data")) if isinstance(root, dict) else None
    except (json.JSONDecodeError, TypeError, IndexError):
        return None
    if not isinstance(store, dict):
        return None

    job_shop = _resolve_nuxt_scalar(payload, store.get("jobShopData"))
    if not isinstance(job_shop, dict):
        return None

    job_shop_id = str(_resolve_nuxt_scalar(payload, job_shop.get("jobShopId")) or "").strip()
    vanity = str(_resolve_nuxt_scalar(payload, job_shop.get("jobShopCompanyVanity")) or "").strip()
    if not job_shop_id or not vanity:
        return None

    api_key = _resolve_nuxt_scalar(
        payload,
        store.get(f"typesenseApiKey-{job_shop_id}-{vanity}")
        or store.get(f"typesenseApiKey-{job_shop_id}"),
    )
    if not api_key:
        for key, value in store.items():
            if key.startswith("typesenseApiKey-"):
                api_key = _resolve_nuxt_scalar(payload, value)
                if isinstance(api_key, str) and len(api_key) > 20:
                    break
        else:
            api_key = None
    if not isinstance(api_key, str) or not api_key:
        return None

    host = (urlparse(careers_url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    tenant_match = re.match(r"careers\.([a-z0-9-]+)\.", host)
    tenant_id = tenant_match.group(1) if tenant_match else ""
    if not tenant_id:
        tenant_id = vanity.rsplit("-", 1)[0]
    if not tenant_id:
        return None
    return api_key, tenant_id, vanity


async def detect_ats_static_async(
    client,
    careers_url: str,
    *,
    _depth: int = 0,
) -> tuple[str | None, str | None]:
    """Async variant used by scrape_jobs bulk fetch."""
    url_detected = _detect_ats_from_careers_url(careers_url)
    if url_detected[0]:
        return url_detected

    try:
        r = await client.get(careers_url, timeout=12.0, follow_redirects=True)
        html = r.text
        page_url = str(r.url)
    except Exception:
        return None, None

    found = _scan_html_for_ats(html)
    if found[0]:
        return found

    if _depth < 2:
        refresh_target = _follow_meta_refresh(html, page_url)
        if refresh_target:
            return await detect_ats_static_async(
                client,
                refresh_target,
                _depth=_depth + 1,
            )

    return None, None
