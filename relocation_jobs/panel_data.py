"""Load and flatten job listings from country JSON files."""

from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from relocation_jobs.build_companies import slug_from_name, sort_companies
from relocation_jobs.catalog_db import (
    load_country as load_country_catalog,
    save_country as save_country_catalog,
    upsert_company as upsert_company_catalog,
)
from relocation_jobs.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
    stamp_job_identity,
)
from relocation_jobs.location_tags import (
    COUNTRY_LABELS as _LOCATION_COUNTRY_LABELS,
    SUGGESTED_CITIES,
    company_matches_location_filter,
    company_visible_for_country_filter,
    format_location_display,
    format_job_location_label,
    job_location_fields,
    job_fails_office_location_gate,
    job_matches_expected_locations,
    company_expected_locations,
    city_match_keys,
    location_key,
    normalize_city_key,
    normalize_country_key,
    normalize_location,
    normalize_locations,
    picker_cities_for_country,
    sync_company_location_fields,
)
from relocation_jobs.paths import COUNTRY_FILE_NAMES

from relocation_jobs.db import (
    clear_company_tracking,
    rename_company_tracking,
    count_jobs_applied_db,
    count_jobs_applied_today_db,
    list_jobs_applied_today_db,
    list_fetch_runs,
    load_job_tracking,
    load_job_status_history,
    reapply_job_db,
    load_company_tracking,
    set_company_applied_db,
    set_company_awaiting_response_db,
    set_job_applied_db,
    sync_company_applied_from_jobs_db,
    set_job_ats_score_db,
    set_job_looking_to_apply_db,
    set_job_not_for_me_db,
    set_job_rejected_db,
    set_job_seen_db,
    set_job_waiting_referral_db,
)

try:
    from relocation_jobs.scrape_jobs import (
        ATS_TYPE_CHOICES,
        KNOWN_ATS,
        detect_ats_for_hint,
        detect_ats_static,
        detect_ats_via_playwright,
    )
except ImportError:
    ATS_TYPE_CHOICES = ()
    KNOWN_ATS = {}
    detect_ats_for_hint = None  # type: ignore
    detect_ats_static = None  # type: ignore
    detect_ats_via_playwright = None  # type: ignore

_file_lock = threading.Lock()


def _normalize_linkedin_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    host = (urlparse(raw).netloc or "").lower()
    if "linkedin.com" not in host:
        raise ValueError("Enter a LinkedIn profile URL (linkedin.com/in/…)")
    return raw


def _normalize_url(url: str) -> str:
    return normalize_job_url(url)


def _job_not_for_me(job: dict) -> bool:
    return bool(job.get("not_for_me"))


def _tracking_key(country: str, company: str, url: str) -> tuple[str, str, str]:
    return (country, company, normalize_job_url(url))


def _tracking_bool(value) -> bool:
    """Coerce DB seen/applied flags (0/1, bool, or str) to bool."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def _resolve_track(
    job_tracking: dict,
    *,
    country: str,
    company_name: str,
    job: dict,
) -> dict:
    """Match tracking for a catalog job by URL, then merge idempotency aliases."""
    direct_key = _tracking_key(country, company_name, job.get("url", ""))
    direct = job_tracking.get(direct_key)
    job_key = job_idempotency_key_for_job(job)
    if not job_key:
        return direct or {}

    siblings: list[dict] = []
    fallback: dict = {}
    for (t_country, t_company, t_url), track in job_tracking.items():
        if t_country != country or t_company != company_name:
            continue
        if job_idempotency_key(t_url) != job_key:
            continue
        siblings.append(track)
        if _tracking_key(t_country, t_company, t_url) != direct_key:
            if (not fallback) or (
                _tracking_bool(track.get("seen")) and not _tracking_bool(fallback.get("seen"))
            ):
                fallback = track

    if direct:
        merged = dict(direct)
    elif fallback:
        merged = dict(fallback)
    elif siblings:
        merged = dict(siblings[0])
    else:
        return {}

    seen_track: dict | None = None
    for track in siblings:
        if not _tracking_bool(track.get("seen")):
            continue
        if not seen_track or (
            (track.get("seen_date") or "") and not (seen_track.get("seen_date") or "")
        ):
            seen_track = track
    if seen_track:
        merged["seen"] = True
        merged["seen_date"] = seen_track.get("seen_date", "") or ""
    return merged


def _resolve_status_history(
    status_history: dict,
    *,
    country: str,
    company_name: str,
    job: dict,
) -> dict[str, list]:
    """Merge apply/reject event lists for a job and its idempotency aliases."""
    empty = {"applied": [], "rejected": [], "applied_events": [], "rejected_events": []}
    direct_key = _tracking_key(country, company_name, job.get("url", ""))
    direct = status_history.get(direct_key, empty)
    job_key = job_idempotency_key_for_job(job)
    if not job_key:
        return {
            "applied": list(direct["applied"]),
            "rejected": list(direct["rejected"]),
            "applied_events": list(direct.get("applied_events") or []),
            "rejected_events": list(direct.get("rejected_events") or []),
        }

    applied_dates: list[str] = list(direct["applied"])
    rejected_dates: list[str] = list(direct["rejected"])
    applied_events: list[dict] = list(direct.get("applied_events") or [])
    rejected_events: list[dict] = list(direct.get("rejected_events") or [])
    seen_applied_events: set[str] = {
        (event.get("at") or event.get("date") or "").strip()
        for event in applied_events
        if (event.get("at") or event.get("date") or "").strip()
    }
    seen_rejected_events: set[str] = {
        (event.get("at") or event.get("date") or "").strip()
        for event in rejected_events
        if (event.get("at") or event.get("date") or "").strip()
    }
    for (t_country, t_company, t_url), hist in status_history.items():
        if t_country != country or t_company != company_name:
            continue
        if job_idempotency_key(t_url) != job_key:
            continue
        if _tracking_key(t_country, t_company, t_url) == direct_key:
            continue
        for date in hist.get("applied") or []:
            if date and date not in applied_dates:
                applied_dates.append(date)
        for date in hist.get("rejected") or []:
            if date and date not in rejected_dates:
                rejected_dates.append(date)
        for event in hist.get("applied_events") or []:
            marker = (event.get("at") or event.get("date") or "").strip()
            if marker and marker not in seen_applied_events:
                seen_applied_events.add(marker)
                applied_events.append(dict(event))
        for event in hist.get("rejected_events") or []:
            marker = (event.get("at") or event.get("date") or "").strip()
            if marker and marker not in seen_rejected_events:
                seen_rejected_events.add(marker)
                rejected_events.append(dict(event))
    applied_dates.sort()
    rejected_dates.sort()
    applied_events.sort(key=lambda event: (event.get("at") or event.get("date") or ""))
    rejected_events.sort(key=lambda event: (event.get("at") or event.get("date") or ""))
    return {
        "applied": applied_dates,
        "rejected": rejected_dates,
        "applied_events": applied_events,
        "rejected_events": rejected_events,
    }


def _latest_applied_at(hist: dict, track: dict | None = None, *, applied: bool = False) -> str:
    events = hist.get("applied_events") or []
    ats = [(event.get("at") or "").strip() for event in events if (event.get("at") or "").strip()]
    if ats:
        return max(ats)
    if applied and track:
        return (track.get("updated_at") or "").strip()
    return ""


def _latest_status_date(dates: list[str]) -> str:
    clean = [(d or "").strip() for d in dates if (d or "").strip()]
    return max(clean) if clean else ""


def _display_status_date(track_date: str, history_dates: list[str]) -> str:
    """Latest ISO date from history plus the current tracking-row date."""
    candidates = [(d or "").strip() for d in (history_dates or []) if (d or "").strip()]
    td = (track_date or "").strip()
    if td:
        candidates.append(td)
    return max(candidates) if candidates else ""


_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CITY_SUFFIX = {
    "uk": re.compile(r",?\s*UK$", re.I),
    "germany": re.compile(r",?\s*(Germany|DE)$", re.I),
    "netherlands": re.compile(r",?\s*(Netherlands|NL|The Netherlands)$", re.I),
    "portugal": re.compile(r",?\s*(Portugal|PT)$", re.I),
}

# Match country names/codes in office location strings (e.g. "Berlin, Germany").
_COUNTRY_FROM_LOCATION: list[tuple[str, re.Pattern[str]]] = [
    ("uk", re.compile(r"\b(?:UK|United Kingdom|England|Scotland|Wales)\b", re.I)),
    ("germany", re.compile(r"\b(?:Germany|Deutschland|DE)\b", re.I)),
    ("netherlands", re.compile(r"\b(?:Netherlands|NL|The Netherlands|Holland)\b", re.I)),
    ("portugal", re.compile(r"\b(?:Portugal|PT)\b", re.I)),
]

# TLD / host hints for careers URLs.
_URL_COUNTRY_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("uk", re.compile(r"\.co\.uk$|\.uk$|careers\.deliveroo\.co\.uk", re.I)),
    ("germany", re.compile(r"\.de$|\.jobs\.personio\.de|karriere\.|stellen\.", re.I)),
    ("netherlands", re.compile(r"\.nl$|\.amsterdam", re.I)),
    ("portugal", re.compile(r"\.pt$|\.lisboa|\.lisbon", re.I)),
]


def today() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


COUNTRY_FILES: dict[str, str] = dict(COUNTRY_FILE_NAMES)

COUNTRY_LABELS = _LOCATION_COUNTRY_LABELS


def country_from_path(path: str) -> str:
    m = re.match(r"(\w+)_companies\.json", Path(path).name)
    return m.group(1) if m else "unknown"


def _load_country_data(country_key: str, *, cache: dict[str, dict] | None = None) -> dict:
    if cache is not None and country_key in cache:
        return cache[country_key]
    data = load_country_catalog(country_key)
    if data is not None:
        for company in data.get("companies") or []:
            sync_company_location_fields(company, catalog_country=country_key)
        result = data
    else:
        result = {
            "source": "",
            "fetched": "",
            "updated": "",
            "jobs_fetched": "",
            "total": 0,
            "companies": [],
        }
    if cache is not None:
        cache[country_key] = result
    return result


def _save_country_data(country_key: str, data: dict) -> None:
    data["total"] = len(data.get("companies") or [])
    save_country_catalog(country_key, data)


def load_country_file(path: Path) -> dict:
    """Legacy helper — prefer _load_country_data(country_key)."""
    from relocation_jobs.catalog_db import country_key_from_filename, load_country_for_path

    country_key, data = load_country_for_path(path)
    if country_key and data.get("companies") is not None:
        return data
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ats_score_value(raw) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        score = int(raw)
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 100:
        return score
    return None


def _title_from_tracked_url(url: str) -> str:
    parsed = urlparse(url)
    for key in ("gh_jid", "jobId", "jid", "id"):
        values = parse_qs(parsed.query).get(key)
        if values and values[0].strip():
            return f"Role {values[0].strip()}"
    path = parsed.path.rstrip("/")
    if path:
        segment = path.split("/")[-1]
        if segment and segment.lower() not in {"jobs", "job", "role", "job-detail", "job-listing"}:
            return segment.replace("-", " ").replace("_", " ").strip()[:120] or "Tracked role"
    return "Tracked role"


def _normalize_ts_for_sort(ts: str) -> str:
    """ISO sort key: date-only YYYY-MM-DD sorts before same-day datetimes."""
    ts = (ts or "").strip()
    if not ts:
        return "0000-00-00T00:00:00"
    if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
        return f"{ts}T00:00:00"
    return ts.replace("Z", "+00:00")


def _job_activity_ts(job: dict) -> str:
    """When the role was first discovered (stable across re-fetches)."""
    return (job.get("fetched") or job.get("last_seen") or "").strip()


def _company_activity_ts(company: dict, stored_jobs: list[dict]) -> str:
    """Company fetch time for sorting — company.updated is stamped on each fetch."""
    updated = (company.get("updated") or "").strip()
    if updated:
        return updated
    job_ts = [_job_activity_ts(j) for j in stored_jobs if _job_activity_ts(j)]
    if job_ts:
        return max(job_ts, key=_normalize_ts_for_sort)
    return (company.get("added") or "").strip()


def _tracked_job_dict(
    track: dict,
    *,
    company_name: str,
    company: dict,
    key: str,
    label: str,
    status_history: dict | None = None,
) -> dict:
    url = track.get("job_url", "")
    title = (track.get("job_title") or "").strip() or _title_from_tracked_url(url)
    applied = bool(track.get("applied"))
    rejected = _tracking_bool(track.get("rejected"))
    looking_to_apply = bool(track.get("looking_to_apply"))
    seen = _tracking_bool(track.get("seen"))
    ats_score = _ats_score_value(track.get("ats_score"))
    hist = (
        _resolve_status_history(
            status_history,
            country=key,
            company_name=company_name,
            job={"url": url},
        )
        if status_history is not None
        else {"applied": [], "rejected": []}
    )
    track_applied_date = track.get("applied_date", "") if applied else ""
    track_rejected_date = track.get("rejected_date", "") if rejected else ""
    return {
        "title": title,
        "url": url,
        "idempotency_key": job_idempotency_key(url),
        "fetched": "",
        "last_seen": "",
        "visa_sponsorship": None,
        "applied": applied,
        "applied_date": _display_status_date(track_applied_date, hist["applied"]),
        "applied_at": _latest_applied_at(hist, track, applied=applied),
        "applied_history": hist["applied"],
        "applied_events": hist.get("applied_events") or [],
        "not_for_me": False,
        "not_for_me_date": "",
        "rejected": rejected,
        "rejected_date": _display_status_date(track_rejected_date, hist["rejected"]),
        "rejected_history": hist["rejected"],
        "looking_to_apply": looking_to_apply,
        "looking_to_apply_date": track.get("looking_to_apply_date", "") or "",
        "seen": seen,
        "seen_date": track.get("seen_date", "") or "",
        "ats_score": ats_score,
        "tracked_only": True,
        "company": company_name,
        "city": company.get("city", ""),
        "size": company.get("size", ""),
        "country": key,
        "country_label": label,
        "careers_url": company.get("careers_url", ""),
        "ats_type": company.get("ats_type", ""),
    }


def _append_tracked_status_jobs(
    jobs: list[dict],
    rejected_jobs: list[dict],
    *,
    key: str,
    company_name: str,
    company: dict,
    label: str,
    job_tracking: dict,
    status_history: dict,
    visa_only: bool,
    hide_position_applied: bool,
    hide_position_rejected: bool,
    position_applied_only: bool,
    position_rejected_only: bool,
    position_looking_to_apply_only: bool = False,
) -> None:
    """Add tracked roles no longer in the catalog (rejected → rejected_jobs, others → jobs)."""
    listed_urls = {_normalize_url(j.get("url", "")) for j in jobs}
    listed_urls.update(_normalize_url(j.get("url", "")) for j in rejected_jobs)
    for (t_country, t_company, t_url), track in job_tracking.items():
        if t_country != key or t_company != company_name:
            continue
        if track.get("not_for_me"):
            continue
        if not (
            track.get("applied")
            or _tracking_bool(track.get("rejected"))
            or track.get("looking_to_apply")
        ):
            continue
        if t_url in listed_urls:
            continue
        job_entry = _tracked_job_dict(
            track,
            company_name=company_name,
            company=company,
            key=key,
            label=label,
            status_history=status_history,
        )
        if visa_only and job_entry.get("visa_sponsorship") is not True:
            continue
        if job_entry.get("rejected"):
            rejected_jobs.append(job_entry)
            continue
        if not _include_job_for_filters(
            job_entry,
            hide_position_applied=hide_position_applied,
            hide_position_rejected=hide_position_rejected,
            position_applied_only=position_applied_only,
            position_rejected_only=position_rejected_only,
            position_looking_to_apply_only=position_looking_to_apply_only,
        ):
            continue
        jobs.append(job_entry)


def _job_dict(
    job: dict,
    *,
    company_name: str,
    company: dict,
    key: str,
    label: str,
    job_tracking: dict | None = None,
    status_history: dict | None = None,
) -> dict:
    url = job.get("url", "")
    track = (
        _resolve_track(job_tracking, country=key, company_name=company_name, job=job)
        if job_tracking is not None
        else {}
    )
    applied = bool(track.get("applied")) if job_tracking is not None else bool(job.get("applied"))
    not_for_me = bool(track.get("not_for_me")) if job_tracking is not None else bool(job.get("not_for_me"))
    not_for_me_date = (
        track.get("not_for_me_date", "") if job_tracking is not None else job.get("not_for_me_date", "")
    ) if not_for_me else ""
    not_for_me_reason = (
        track.get("not_for_me_reason", "") if job_tracking is not None else job.get("not_for_me_reason", "")
    ) if not_for_me else ""
    rejected = (
        _tracking_bool(track.get("rejected"))
        if job_tracking is not None
        else _tracking_bool(job.get("rejected"))
    )
    waiting_referral = (
        bool(track.get("waiting_referral"))
        if job_tracking is not None
        else bool(job.get("waiting_referral"))
    )
    waiting_referral_date = (
        track.get("waiting_referral_date", "")
        if waiting_referral and job_tracking is not None
        else (job.get("waiting_referral_date", "") if waiting_referral else "")
    )
    referral_linkedin_url = (
        track.get("referral_linkedin_url", "")
        if job_tracking is not None
        else job.get("referral_linkedin_url", "")
    ) if waiting_referral else ""
    ats_score = (
        _ats_score_value(track.get("ats_score"))
        if job_tracking is not None
        else _ats_score_value(job.get("ats_score"))
    )
    seen = (
        _tracking_bool(track.get("seen"))
        if job_tracking is not None
        else _tracking_bool(job.get("seen"))
    )
    seen_date = (
        track.get("seen_date", "") if job_tracking is not None else job.get("seen_date", "")
    )
    looking_to_apply = (
        bool(track.get("looking_to_apply")) if job_tracking is not None else bool(job.get("looking_to_apply"))
    )
    looking_to_apply_date = (
        track.get("looking_to_apply_date", "") if job_tracking is not None else job.get("looking_to_apply_date", "")
    )
    hist = (
        _resolve_status_history(
            status_history,
            country=key,
            company_name=company_name,
            job=job,
        )
        if status_history is not None
        else {"applied": [], "rejected": []}
    )
    track_applied_date = (
        track.get("applied_date", "") if applied and job_tracking is not None else (
            job.get("applied_date", "") if applied else ""
        )
    )
    track_rejected_date = (
        track.get("rejected_date", "") if rejected and job_tracking is not None else (
            job.get("rejected_date", "") if rejected else ""
        )
    )
    return {
        "title": job.get("title", ""),
        "url": url,
        "idempotency_key": job_idempotency_key_for_job(job),
        "fetched": job.get("fetched", ""),
        "last_seen": job.get("last_seen", ""),
        "visa_sponsorship": job.get("visa_sponsorship"),
        **job_location_fields(job),
        "applied": applied,
        "applied_date": _display_status_date(track_applied_date, hist["applied"]),
        "applied_at": _latest_applied_at(hist, track, applied=applied),
        "applied_history": hist["applied"],
        "applied_events": hist.get("applied_events") or [],
        "not_for_me": not_for_me,
        "not_for_me_date": not_for_me_date or "",
        "not_for_me_reason": not_for_me_reason or "",
        "rejected": rejected,
        "rejected_date": _display_status_date(track_rejected_date, hist["rejected"]),
        "rejected_history": hist["rejected"],
        "waiting_referral": waiting_referral,
        "waiting_referral_date": waiting_referral_date or "",
        "referral_linkedin_url": referral_linkedin_url or "",
        "ats_score": ats_score,
        "seen": seen,
        "seen_date": seen_date or "",
        "looking_to_apply": looking_to_apply,
        "looking_to_apply_date": looking_to_apply_date or "",
        "company": company_name,
        "city": company.get("city", ""),
        "size": company.get("size", ""),
        "country": key,
        "country_label": label,
        "careers_url": company.get("careers_url", ""),
        "ats_type": company.get("ats_type", ""),
    }


def _derive_company_applied(
    key: str,
    company_name: str,
    stored_jobs: list[dict],
    job_tracking: dict,
) -> tuple[bool, str, int, str]:
    """Company is applied when any tracked position for it is applied."""
    dates: list[str] = []
    applied_ats: list[str] = []
    seen_urls: set[str] = set()

    for job in stored_jobs:
        url = normalize_job_url(job.get("url", ""))
        seen_urls.add(url)
        track = job_tracking.get(_tracking_key(key, company_name, url), {})
        if track.get("applied"):
            dates.append((track.get("applied_date") or "").strip())
            applied_at = (track.get("updated_at") or "").strip()
            if applied_at:
                applied_ats.append(applied_at)

    for (t_country, t_company, t_url), track in job_tracking.items():
        if t_country != key or t_company != company_name or t_url in seen_urls:
            continue
        if track.get("applied"):
            dates.append((track.get("applied_date") or "").strip())
            applied_at = (track.get("updated_at") or "").strip()
            if applied_at:
                applied_ats.append(applied_at)

    if not dates:
        return False, "", 0, ""

    non_empty = [d for d in dates if d]
    applied_date = min(non_empty) if non_empty else ""
    company_applied_at = min(applied_ats) if applied_ats else ""
    return True, applied_date, len(dates), company_applied_at


def _include_job_for_filters(
    job: dict,
    *,
    hide_position_applied: bool = False,
    hide_position_rejected: bool = False,
    position_applied_only: bool = False,
    position_rejected_only: bool = False,
    position_looking_to_apply_only: bool = False,
) -> bool:
    applied = bool(job.get("applied"))
    rejected = bool(job.get("rejected"))
    looking_to_apply = bool(job.get("looking_to_apply"))
    if hide_position_applied and applied:
        return False
    if hide_position_rejected and rejected:
        return False
    if position_applied_only and not applied:
        return False
    if position_rejected_only and not rejected:
        return False
    if position_looking_to_apply_only and not looking_to_apply:
        return False
    return True


def flatten_companies(
    country_key: str | None = None,
    *,
    visa_only: bool = False,
    hide_applied: bool = False,
    hide_empty: bool = False,
    not_applied_only: bool = False,
    hide_position_applied: bool = False,
    hide_position_rejected: bool = False,
    position_applied_only: bool = False,
    position_rejected_only: bool = False,
    position_looking_to_apply_only: bool = False,
    fetch_ok_only: bool = False,
    fetch_problem_only: bool = False,
    location: str | None = None,
    city: str | None = None,
    user_id: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Return (companies, file_meta) sorted by latest job fetch date descending.

    Job/company applied and not-for-me state comes from the database when
    ``user_id`` is set; company/job listings come from the catalog DB (SQLite).
    """
    companies_out: list[dict] = []
    file_meta: list[dict] = []
    fetch_problem_count = 0

    job_tracking = load_job_tracking(user_id) if user_id else {}
    company_tracking = load_company_tracking(user_id) if user_id else {}
    status_history = load_job_status_history(user_id) if user_id else {}

    keys = [country_key] if country_key and country_key != "all" else list(COUNTRY_FILES)
    company_keys = list(COUNTRY_FILES)

    location_filter = (location or city or "").strip() or None
    country_cache: dict[str, dict] = {}

    for key in keys:
        filename = COUNTRY_FILES.get(key)
        if not filename:
            continue

        data = _load_country_data(key, cache=country_cache)
        if not data.get("companies") and not data.get("source"):
            continue

        label = COUNTRY_LABELS.get(key, key)
        file_meta.append({
            "country": key,
            "label": label,
            "file": filename,
            "fetched": data.get("fetched", ""),
            "updated": data.get("updated", data.get("jobs_fetched", "")),
            "jobs_fetched": data.get("jobs_fetched", ""),
            "total_companies": data.get("total", len(data.get("companies", []))),
            "source": data.get("source", ""),
            "last_fetch_new_jobs": int(data.get("last_fetch_new_jobs") or 0),
        })

    for key in company_keys:
        filename = COUNTRY_FILES.get(key)
        if not filename:
            continue

        data = _load_country_data(key, cache=country_cache)
        if not data.get("companies") and not data.get("source"):
            continue

        label = COUNTRY_LABELS.get(key, key)

        for company in data.get("companies", []):
            company_name = company.get("name", "")
            if country_key and country_key != "all":
                if not company_visible_for_country_filter(
                    company, country_key, catalog_country=key
                ):
                    continue
            if location_filter and not company_matches_location_filter(
                company,
                location_filter,
                catalog_country=key,
            ):
                continue
            if company.get("fetch_problem"):
                fetch_problem_count += 1
            if user_id:
                company_applied, company_applied_date, _company_applied_positions, company_applied_at = (
                    _derive_company_applied(
                        key,
                        company_name,
                        company.get("matching_jobs") or [],
                        job_tracking,
                    )
                )
            else:
                company_applied = bool(company.get("company_applied"))
                company_applied_date = (
                    company.get("company_applied_date", "")
                    if company_applied else ""
                )
                _company_applied_positions = 0
                company_applied_at = ""

            company_track = company_tracking.get((key, company_name), {})
            awaiting_response = bool(company_track.get("awaiting_response")) if user_id else False
            awaiting_response_date = (
                (company_track.get("awaiting_response_date") or "").strip()
                if awaiting_response and user_id
                else ""
            )

            if hide_applied and company_applied:
                continue
            if fetch_ok_only and not (
                company.get("fetch_ok") and not company.get("fetch_problem")
            ):
                continue
            if fetch_problem_only and not company.get("fetch_problem"):
                continue

            stored_jobs = company.get("matching_jobs") or []
            stored_job_count = len(stored_jobs)
            jobs: list[dict] = []
            not_for_me_jobs: list[dict] = []
            rejected_jobs: list[dict] = []
            positions_not_for_me = 0
            positions_hidden_by_visa = 0
            for job in stored_jobs:
                track = _resolve_track(
                    job_tracking,
                    country=key,
                    company_name=company_name,
                    job=job,
                )
                if user_id:
                    if track.get("not_for_me"):
                        positions_not_for_me += 1
                        not_for_me_jobs.append(_job_dict(
                            job,
                            company_name=company_name,
                            company=company,
                            key=key,
                            label=label,
                            job_tracking=job_tracking,
                            status_history=status_history,
                        ))
                        continue
                elif _job_not_for_me(job):
                    positions_not_for_me += 1
                    not_for_me_jobs.append(_job_dict(
                        job,
                        company_name=company_name,
                        company=company,
                        key=key,
                        label=label,
                        job_tracking=None,
                    ))
                    continue
                fails_gate, _ = job_fails_office_location_gate(
                    job, company, catalog_country=key
                )
                if fails_gate:
                    positions_not_for_me += 1
                    wrong_entry = _job_dict(
                        job,
                        company_name=company_name,
                        company=company,
                        key=key,
                        label=label,
                        job_tracking=job_tracking if user_id else None,
                        status_history=status_history if user_id else None,
                    )
                    wrong_entry["not_for_me"] = True
                    if not wrong_entry.get("not_for_me_reason"):
                        wrong_entry["not_for_me_reason"] = "wrong_location"
                    not_for_me_jobs.append(wrong_entry)
                    continue
                if visa_only and job.get("visa_sponsorship") is not True:
                    positions_hidden_by_visa += 1
                    continue
                job_entry = _job_dict(
                    job,
                    company_name=company_name,
                    company=company,
                    key=key,
                    label=label,
                    job_tracking=job_tracking if user_id else None,
                    status_history=status_history if user_id else None,
                )
                if job_entry.get("rejected"):
                    rejected_jobs.append(job_entry)
                    continue
                if not _include_job_for_filters(
                    job_entry,
                    hide_position_applied=hide_position_applied,
                    hide_position_rejected=hide_position_rejected,
                    position_applied_only=position_applied_only,
                    position_rejected_only=position_rejected_only,
                    position_looking_to_apply_only=position_looking_to_apply_only,
                ):
                    continue
                jobs.append(job_entry)

            if user_id:
                _append_tracked_status_jobs(
                    jobs,
                    rejected_jobs,
                    key=key,
                    company_name=company_name,
                    company=company,
                    label=label,
                    job_tracking=job_tracking,
                    status_history=status_history,
                    visa_only=visa_only,
                    hide_position_applied=hide_position_applied,
                    hide_position_rejected=hide_position_rejected,
                    position_applied_only=position_applied_only,
                    position_rejected_only=position_rejected_only,
                    position_looking_to_apply_only=position_looking_to_apply_only,
                )

            if visa_only and not jobs and not rejected_jobs:
                continue
            if position_rejected_only:
                if not rejected_jobs:
                    continue
            elif (position_applied_only or position_looking_to_apply_only) and not jobs:
                continue
            if hide_empty and not jobs and not not_for_me_jobs and not rejected_jobs:
                continue
            if not_applied_only and (company_applied or not jobs):
                continue

            sort_ts = _company_activity_ts(company, stored_jobs)
            newest_job_fetched = sort_ts
            visible_ts = [_job_activity_ts(j) for j in jobs if _job_activity_ts(j)]
            latest_fetch = max(visible_ts, default="") or sort_ts
            positions_applied = sum(1 for j in jobs if j.get("applied"))
            positions_rejected = len(rejected_jobs)
            if user_id:
                positions_applied_all = _company_applied_positions
            else:
                positions_applied_all = positions_applied

            companies_out.append({
                "name": company_name,
                "city": company.get("city", ""),
                "cities": company.get("cities") or [],
                "locations": company.get("locations") or [],
                "size": company.get("size", ""),
                "country": key,
                "country_label": label,
                "careers_url": company.get("careers_url", ""),
                "ats_type": company.get("ats_type", ""),
                "ats_url": company.get("ats_url", ""),
                "fetch_problem": bool(company.get("fetch_problem")),
                "fetch_problem_date": company.get("fetch_problem_date", ""),
                "fetch_ok": bool(company.get("fetch_ok")),
                "fetch_ok_date": company.get("fetch_ok_date", ""),
                "company_applied": company_applied,
                "company_applied_date": company_applied_date,
                "company_applied_at": company_applied_at,
                "awaiting_response": awaiting_response,
                "awaiting_response_date": awaiting_response_date,
                "jobs": jobs,
                "not_for_me_jobs": not_for_me_jobs,
                "rejected_jobs": rejected_jobs,
                "job_count": len(jobs),
                "stored_job_count": stored_job_count,
                "positions_applied": positions_applied,
                "positions_applied_all": positions_applied_all,
                "positions_rejected": positions_rejected,
                "positions_not_for_me": positions_not_for_me,
                "positions_hidden_by_visa": positions_hidden_by_visa,
                "updated": company.get("updated", ""),
                "latest_fetched": latest_fetch,
                "newest_job_fetched": newest_job_fetched,
            })

    return companies_out, file_meta, fetch_problem_count


def flatten_jobs(
    country_key: str | None = None,
    *,
    visa_only: bool = False,
    hide_applied: bool = False,
    hide_empty: bool = False,
    not_applied_only: bool = False,
    hide_position_applied: bool = False,
    hide_position_rejected: bool = False,
    position_applied_only: bool = False,
    position_rejected_only: bool = False,
    fetch_ok_only: bool = False,
    fetch_problem_only: bool = False,
    user_id: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Flat job list (legacy); prefer flatten_companies for the panel."""
    companies, file_meta, _fetch_problem_count = flatten_companies(
        country_key,
        visa_only=visa_only,
        hide_applied=hide_applied,
        hide_empty=hide_empty,
        not_applied_only=not_applied_only,
        hide_position_applied=hide_position_applied,
        hide_position_rejected=hide_position_rejected,
        position_applied_only=position_applied_only,
        position_rejected_only=position_rejected_only,
        fetch_ok_only=fetch_ok_only,
        fetch_problem_only=fetch_problem_only,
        user_id=user_id,
    )
    jobs: list[dict] = []
    for company in companies:
        jobs.extend(company["jobs"])
    jobs.sort(key=lambda j: _normalize_ts_for_sort(_job_activity_ts(j)), reverse=True)
    return jobs, file_meta


def compute_stats(
    companies: list[dict],
    file_meta: list[dict],
    *,
    fetch_problem_count: int = 0,
    user_id: int | None = None,
    country_key: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    total_jobs = sum(c.get("job_count", len(c.get("jobs", []))) for c in companies)
    visa_count = sum(
        1
        for c in companies
        for j in c.get("jobs", [])
        if j.get("visa_sponsorship") is True
    )
    positions_applied = (
        count_jobs_applied_db(user_id, country=country_key)
        if user_id
        else sum(
            c.get("positions_applied_all", c.get("positions_applied", 0)) for c in companies
        )
    )
    positions_rejected = sum(c.get("positions_rejected", 0) for c in companies)
    company_applied_count = sum(
        1 for c in companies if c.get("company_applied") or c.get("positions_applied_all", 0) > 0
    )
    not_for_me_count = sum(c.get("positions_not_for_me", 0) for c in companies)
    latest_fetch = max(
        (c.get("newest_job_fetched") or c.get("latest_fetched") or "" for c in companies),
        default="",
    )
    latest_fetch_new_jobs = sum(int(m.get("last_fetch_new_jobs") or 0) for m in file_meta)
    positions_applied_today = (
        count_jobs_applied_today_db(
            user_id,
            country=country_key,
            timezone_name=timezone_name,
        )
        if user_id
        else 0
    )
    applied_today_jobs = (
        list_jobs_applied_today_db(
            user_id,
            country=country_key,
            timezone_name=timezone_name,
        )
        if user_id
        else []
    )
    recent_fetch_runs = (
        list_fetch_runs(user_id, country=country_key, limit=5)
        if user_id
        else []
    )
    by_country: dict[str, int] = {}
    for c in companies:
        by_country[c["country"]] = by_country.get(c["country"], 0) + c.get("job_count", 0)
    return {
        "total_jobs": total_jobs,
        "companies_with_jobs": len(companies),
        "visa_sponsored": visa_count,
        "applied": company_applied_count,
        "positions_applied": positions_applied,
        "positions_applied_today": positions_applied_today,
        "applied_today_jobs": applied_today_jobs,
        "positions_rejected": positions_rejected,
        "not_for_me": not_for_me_count,
        "fetch_problems": fetch_problem_count,
        "latest_job_fetch": latest_fetch,
        "latest_fetch_new_jobs": latest_fetch_new_jobs,
        "recent_fetch_runs": recent_fetch_runs,
        "by_country": by_country,
        "files": file_meta,
    }


def find_company_in_data(
    data: dict,
    company_name: str,
) -> dict | None:
    target = company_name.strip().lower()
    if not target:
        return None
    for company in data.get("companies", []):
        if company.get("name", "").strip().lower() == target:
            return company
    return None


def touch_company_fetch_time(country_key: str, company_name: str) -> str:
    """Stamp company.updated with UTC seconds when a fetch starts (sort order)."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if country_key not in COUNTRY_FILES:
        raise ValueError(f"Unknown country: {country_key}")

    with _file_lock:
        data = _load_country_data(country_key)
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")
        ts = now_iso()
        company["updated"] = ts
        upsert_company_catalog(country_key, company, updated=ts)
        return ts


def resolve_company_name(country_key: str, company_name: str) -> str:
    """Return the canonical company name from the catalog (exact casing)."""
    data = _load_country_data(country_key)
    company = find_company_in_data(data, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return company["name"]


def find_job_in_data(
    data: dict,
    company_name: str,
    job_url: str,
) -> dict | None:
    target_url = _normalize_url(job_url)
    target_key = job_idempotency_key(job_url)
    for company in data.get("companies", []):
        if company.get("name", "").lower() != company_name.lower():
            continue
        for job in company.get("matching_jobs") or []:
            if _normalize_url(job.get("url", "")) == target_url:
                return job
            if target_key and job_idempotency_key_for_job(job) == target_key:
                return job
    return None


def set_job_applied(
    country_key: str,
    company_name: str,
    job_url: str,
    applied: bool,
    *,
    user_id: int,
) -> dict:
    """Set or clear applied status on a specific job (stored in the database)."""
    data = _load_country_data(country_key)
    job = find_job_in_data(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    result = set_job_applied_db(
        user_id,
        country_key,
        company_name,
        job_url,
        applied,
        job_title=job.get("title", ""),
    )
    sync_company_applied_from_jobs_db(user_id, country_key, company_name)
    if applied:
        set_company_awaiting_response_db(
            user_id,
            country_key,
            company_name,
            True,
            preserve_date=True,
        )
    return result


def set_job_rejected(
    country_key: str,
    company_name: str,
    job_url: str,
    rejected: bool,
    *,
    user_id: int,
) -> dict:
    """Set or clear rejection status on a specific job (stored in the database)."""
    data = _load_country_data(country_key)
    job = find_job_in_data(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return set_job_rejected_db(
        user_id,
        country_key,
        company_name,
        job_url,
        rejected,
        job_title=job.get("title", ""),
    )


def set_job_reapply(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
) -> dict:
    """Clear active rejection and return the role to the main positions list."""
    data = _load_country_data(country_key)
    job = find_job_in_data(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return reapply_job_db(user_id, country_key, company_name, job_url)


def set_job_waiting_referral(
    country_key: str,
    company_name: str,
    job_url: str,
    waiting_referral: bool,
    *,
    user_id: int,
    linkedin_url: str = "",
) -> dict:
    """Mark a job as waiting for referral and store the referrer LinkedIn URL."""
    data = _load_country_data(country_key)
    job = find_job_in_data(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    normalized_linkedin = _normalize_linkedin_url(linkedin_url) if waiting_referral else ""
    return set_job_waiting_referral_db(
        user_id,
        country_key,
        company_name,
        job_url,
        waiting_referral,
        linkedin_url=normalized_linkedin,
        job_title=job.get("title", ""),
    )


def set_job_ats_score(
    country_key: str,
    company_name: str,
    job_url: str,
    ats_score: int | None,
    *,
    user_id: int,
) -> dict:
    """Set or clear ATS compatibility score (0–100) on a specific job."""
    data = _load_country_data(country_key)
    if find_company_in_data(data, company_name) is None:
        raise LookupError(f"Company not found: {company_name}")
    job = find_job_in_data(data, company_name, job_url)
    title = job.get("title", "") if job else ""
    return set_job_ats_score_db(
        user_id,
        country_key,
        company_name,
        job_url,
        ats_score,
        job_title=title,
    )


def set_job_looking_to_apply(
    country_key: str,
    company_name: str,
    job_url: str,
    looking_to_apply: bool,
    *,
    user_id: int,
) -> dict:
    """Set or clear looking-to-apply status on a specific job."""
    data = _load_country_data(country_key)
    job = find_job_in_data(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return set_job_looking_to_apply_db(
        user_id,
        country_key,
        company_name,
        job_url,
        looking_to_apply,
        job_title=job.get("title", ""),
    )


def set_job_seen(
    country_key: str,
    company_name: str,
    job_url: str,
    seen: bool = True,
    *,
    user_id: int,
) -> dict:
    """Mark or clear the saw-before tag. Preserves original seen_date on repeat marks."""
    data = _load_country_data(country_key)
    job = find_job_in_data(data, company_name, job_url)
    return set_job_seen_db(
        user_id,
        country_key,
        company_name,
        job_url,
        seen,
        job_title=job.get("title", "") if job else "",
    )


def set_company_applied(
    country_key: str,
    company_name: str,
    applied: bool,
    *,
    user_id: int,
) -> dict:
    """Set or clear company-level applied (stored in the database)."""
    data = _load_country_data(country_key)
    company = find_company_in_data(data, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return set_company_applied_db(user_id, country_key, company_name, applied)


def set_company_awaiting_response(
    country_key: str,
    company_name: str,
    awaiting: bool,
    *,
    user_id: int,
) -> dict:
    """Set or clear awaiting-response state for a company."""
    data = _load_country_data(country_key)
    company = find_company_in_data(data, company_name)
    if company is None:
        raise LookupError(f"Company not found: {company_name}")
    return set_company_awaiting_response_db(
        user_id,
        country_key,
        company_name,
        awaiting,
    )


def set_job_not_for_me(
    country_key: str,
    company_name: str,
    job_url: str,
    *,
    user_id: int,
    not_for_me: bool = True,
    reason: str | None = None,
) -> dict:
    """Mark or unmark a job as not for me (stored in the database)."""
    data = _load_country_data(country_key)
    job = find_job_in_data(data, company_name, job_url)
    if job is None:
        raise LookupError(f"Job not found: {company_name} — {job_url[:80]}")
    return set_job_not_for_me_db(
        user_id,
        country_key,
        company_name,
        job_url,
        not_for_me=not_for_me,
        reason=reason,
    )


def reconcile_wrong_location_hides(
    user_id: int,
    *,
    country_key: str | None = None,
    city_label: str | None = None,
) -> int:
    """Restore jobs hidden as wrong_location when they now match office tags."""
    from relocation_jobs.db import get_connection

    query = """
        SELECT country, company_name, job_url
        FROM job_tracking
        WHERE user_id = %s
          AND not_for_me = 1
          AND not_for_me_reason = 'wrong_location'
    """
    params: list = [user_id]
    if country_key:
        query += " AND country = %s"
        params.append(country_key)

    rows = get_connection().execute(query, params).fetchall()
    target_city_keys = city_match_keys(city_label) if city_label else set()
    restored = 0

    for row in rows:
        country = row["country"]
        company_name = row["company_name"]
        job_url = row["job_url"]

        data = _load_country_data(country)
        if not data:
            continue
        company = find_company_in_data(data, company_name)
        if company is None:
            continue
        job = find_job_in_data(data, company_name, job_url)
        if job is None:
            continue

        expected = company_expected_locations(company, catalog_country=country)
        if target_city_keys:
            office_keys = {
                key
                for loc in expected
                for key in city_match_keys(loc["city"])
            }
            if not (office_keys & target_city_keys):
                continue

        ok, _ = job_matches_expected_locations(job, expected)
        if not ok:
            continue

        set_job_not_for_me_db(
            user_id,
            country,
            company_name,
            job_url,
            not_for_me=False,
        )
        restored += 1

    return restored


def normalize_careers_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("careers_url is required")
    if not url.startswith("http"):
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError("Invalid careers URL")
    return url


def _format_size_part(n: int) -> str:
    return f"{n:,}" if n >= 1000 else str(n)


def normalize_company_size(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").replace(",", "")).strip().lower()
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)", cleaned)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return f"{_format_size_part(lo)}-{_format_size_part(hi)}"
    m = re.search(r"(\d+)\+", cleaned)
    if m:
        return f"{_format_size_part(int(m.group(1)))}+"
    return ""


def parse_company_cities(company: dict, *, catalog_country: str = "") -> list[str]:
    sync_company_location_fields(company, catalog_country=catalog_country)
    return company.get("cities") or []


def list_company_cities(country_key: str | None = None) -> list[str]:
    return [loc["city"] for loc in list_company_locations(country_key)]


def list_company_locations(
    country_key: str | None = None,
    *,
    for_picker: bool = False,
) -> list[dict]:
    """Return location options for the header filter or company tag picker."""
    keyed: dict[str, dict] = {}
    filter_country = (
        normalize_country_key(country_key)
        if country_key and country_key != "all"
        else ""
    )

    def add(country: str, city: str) -> None:
        loc = normalize_location(country, city)
        if not loc:
            return
        if filter_country and not for_picker:
            if normalize_country_key(loc["country"]) != filter_country:
                return
        keyed.setdefault(loc["key"], loc)

    if for_picker:
        for key in COUNTRY_FILES:
            for city in picker_cities_for_country(key):
                add(key, city)

    for key in COUNTRY_FILES:
        data = _load_country_data(key)
        for company in data.get("companies") or []:
            locations = normalize_locations(
                company.get("locations"),
                catalog_country=key,
                legacy_cities=company.get("cities")
                if isinstance(company.get("cities"), list)
                else None,
                legacy_city=company.get("city", ""),
            )
            for loc in locations:
                add(loc["country"], loc["city"])

    return sorted(
        keyed.values(),
        key=lambda loc: (loc["country_label"], loc["city"].casefold()),
    )


def _clean_city(raw: str, country_key: str) -> str:
    city = raw.strip()
    pat = _CITY_SUFFIX.get(country_key)
    if pat:
        city = pat.sub("", city).strip()
    return city.split(",")[0].strip() if city else ""


def parse_country_from_location(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    for key, pattern in _COUNTRY_FROM_LOCATION:
        if pattern.search(text):
            return key
    if "," in text:
        suffix = text.rsplit(",", 1)[-1].strip()
        for key, pattern in _COUNTRY_FROM_LOCATION:
            if pattern.search(suffix):
                return key
    return None


def detect_country_from_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    full = url.lower()
    for key, pattern in _URL_COUNTRY_HINTS:
        if pattern.search(host) or pattern.search(full):
            return key
    return None


def resolve_country_key(
    name: str,
    careers_url: str,
    *,
    hint: str | None = None,
) -> tuple[str, dict]:
    """
    Pick the JSON file country for a new company.

    Uses explicit hint when given (not ``auto``), else relocate.me office
    locations, else careers URL TLD/host hints.
    """
    hint = (hint or "").strip().lower()
    if hint and hint not in ("auto", "all") and hint in COUNTRY_FILES:
        return hint, {}

    meta = fetch_relocate_metadata(name)
    if meta.get("country"):
        return meta["country"], meta

    from_url = detect_country_from_url(careers_url)
    if from_url:
        return from_url, meta

    raise ValueError(
        "Could not detect country. Choose one in the form or use a careers URL "
        "with a clear region (e.g. .de, .nl, .co.uk, .pt)."
    )


def fetch_relocate_metadata(name: str, country_key: str | None = None) -> dict:
    """Best-effort city, size, and country from relocate.me company page."""
    slug = slug_from_name(name)
    for candidate in {slug, slug.replace("-", "")}:
        try:
            r = requests.get(
                f"https://relocate.me/companies-hiring/{candidate}",
                headers=_FETCH_HEADERS,
                timeout=15,
            )
            if r.status_code >= 400:
                continue
        except requests.RequestException:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        locations = [
            el.get_text(" ", strip=True)
            for el in soup.select(".company-location")
            if el.get_text(strip=True)
        ]

        country = country_key
        city = ""
        if not country:
            for loc in locations:
                country = parse_country_from_location(loc)
                if country:
                    city = _clean_city(loc, country)
                    break
        elif locations:
            city = _clean_city(locations[0], country)

        if not city and locations:
            city = _clean_city(locations[0], country or "uk")

        size = ""
        for heading in soup.select(".company-facts__heading"):
            label = heading.get_text(strip=True).lower()
            if "company size" not in label:
                continue
            block = heading.find_next_sibling()
            if block:
                size = normalize_company_size(block.get_text(" ", strip=True))

        if city or size or country:
            return {
                "city": city,
                "size": size,
                "country": country or "",
                "relocate_slug": candidate,
            }
    return {}


def list_ats_types() -> list[dict]:
    return [{"id": key, "label": label} for key, label in ATS_TYPE_CHOICES]


def detect_ats_for_company(
    name: str,
    careers_url: str,
    *,
    ats_hint: str | None = None,
) -> tuple[str, str]:
    """Detect ATS type and API/board URL from a careers page."""
    hint = (ats_hint or "").strip().lower()
    if hint and hint not in ("auto", "") and detect_ats_for_hint:
        ats_type, ats_url = detect_ats_for_hint(name, careers_url, hint)
        if ats_type:
            return _finalize_detected_ats(name, ats_type, ats_url)

    ats_type: str | None = None
    ats_url = ""

    if name in KNOWN_ATS:
        ats_type, ats_url = KNOWN_ATS[name]
    elif detect_ats_static:
        ats_type, ats_url = detect_ats_static(careers_url)
        if not ats_type and detect_ats_via_playwright:
            ats_type, ats_url = detect_ats_via_playwright(careers_url)

    return _finalize_detected_ats(name, ats_type or "", ats_url or "")


def _finalize_detected_ats(name: str, ats_type: str, ats_url: str) -> tuple[str, str]:
    if ats_type and ats_url:
        slug = ats_url.rstrip("/").split("/")[-1].split("?")[0]
        is_proxy = "careers-analytics" in ats_url
        is_bad_slug = slug in ("embed", "jobs", "")
        if (is_bad_slug or is_proxy) and name in KNOWN_ATS:
            ats_type, ats_url = KNOWN_ATS[name]
    return ats_type or "", ats_url or ""


def enrich_new_company(
    name: str,
    careers_url: str,
    country_key: str,
    *,
    ats_hint: str | None = None,
) -> dict:
    """Build a full company record from name + careers URL."""
    careers_url = normalize_careers_url(careers_url)
    meta = fetch_relocate_metadata(name, country_key)
    ats_type, ats_url = detect_ats_for_company(name, careers_url, ats_hint=ats_hint)
    now = today()

    company: dict = {
        "name": name.strip(),
        "city": meta.get("city", ""),
        "size": meta.get("size", ""),
        "careers_url": careers_url,
        "matching_jobs": [],
        "ats_type": ats_type,
        "ats_url": ats_url,
        "sources": ["panel"],
        "added": now,
        "updated": now,
    }
    sync_company_location_fields(company, catalog_country=country_key)
    return company


def add_company(
    name: str,
    careers_url: str,
    country_key: str | None = None,
    *,
    country_keys: list[str] | None = None,
    ats_hint: str | None = None,
    locations: list[dict] | None = None,
) -> dict:
    """
    Add a company to the catalog after enriching metadata.
    Country is auto-detected when not provided.
    Raises ValueError for bad input, LookupError if duplicate name.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Company name is required")

    careers_url = normalize_careers_url(careers_url)
    hint = None
    if country_keys:
        cleaned_keys = [
            key.strip().lower()
            for key in country_keys
            if (key or "").strip().lower() in COUNTRY_FILES
        ]
        hint = cleaned_keys[0] if cleaned_keys else None
    elif country_key and country_key not in ("auto", "all", ""):
        hint = country_key.strip().lower()

    resolved_country, _meta = resolve_country_key(
        name, careers_url, hint=hint
    )

    filename = COUNTRY_FILES.get(resolved_country)
    if not filename:
        raise ValueError(f"Unknown country: {resolved_country}")

    company = enrich_new_company(
        name,
        careers_url,
        resolved_country,
        ats_hint=ats_hint,
    )

    if locations is not None:
        cleaned: list[dict] = []
        seen: set[str] = set()
        for item in locations:
            if not isinstance(item, dict):
                continue
            loc = normalize_location(item.get("country", ""), item.get("city", ""))
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)
        cleaned.sort(key=lambda loc: (loc["country_label"], loc["city"].casefold()))
        company["locations"] = cleaned
        sync_company_location_fields(company, catalog_country=resolved_country)

    with _file_lock:
        data = _load_country_data(resolved_country)
        for existing in data.get("companies", []):
            if existing.get("name", "").lower() == name.lower():
                raise LookupError(f"Company already exists: {name}")

        data.setdefault("companies", []).append(company)
        data["companies"] = sort_companies(data["companies"])
        data["updated"] = today()
        _save_country_data(resolved_country, data)

    return {
        "country": resolved_country,
        "country_label": COUNTRY_LABELS.get(resolved_country, resolved_country),
        "file": filename,
        **company,
    }


def rename_company(
    country_key: str,
    company_name: str,
    new_name: str,
) -> dict:
    """Rename a company in the catalog and migrate user tracking keys."""
    company_name = (company_name or "").strip()
    new_name = (new_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")
    if not new_name:
        raise ValueError("New company name is required")
    if company_name.casefold() == new_name.casefold():
        raise ValueError("New name must be different from the current name")

    filename = COUNTRY_FILES.get(country_key)
    if not filename:
        raise ValueError(f"Unknown country: {country_key}")

    with _file_lock:
        data = _load_country_data(country_key)
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_old = company.get("name", company_name)
        for existing in data.get("companies") or []:
            if existing is company:
                continue
            if existing.get("name", "").strip().casefold() == new_name.casefold():
                raise LookupError(f"Company already exists: {new_name}")

        company["name"] = new_name
        company["updated"] = today()
        data["companies"] = sort_companies(data.get("companies") or [])
        data["updated"] = today()
        _save_country_data(country_key, data)

    rename_company_tracking(country_key, canonical_old, new_name)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "file": filename,
        "company": new_name,
        "previous_name": canonical_old,
    }


def update_company_careers(
    country_key: str,
    company_name: str,
    careers_url: str,
    *,
    redetect_ats: bool = True,
) -> dict:
    """Update a company's careers URL and optionally re-detect ATS settings."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")

    filename = COUNTRY_FILES.get(country_key)
    if not filename:
        raise ValueError(f"Unknown country: {country_key}")

    careers_url = normalize_careers_url(careers_url)

    with _file_lock:
        data = _load_country_data(country_key)
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        company["careers_url"] = careers_url
        if redetect_ats:
            ats_type, ats_url = detect_ats_for_company(canonical_name, careers_url)
            company["ats_type"] = ats_type
            company["ats_url"] = ats_url
        company["updated"] = today()
        data["updated"] = today()
        _save_country_data(country_key, data)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": canonical_name,
        "careers_url": careers_url,
        "ats_type": company.get("ats_type", ""),
        "ats_url": company.get("ats_url", ""),
        "redetect_ats": redetect_ats,
    }


def update_company_city(
    country_key: str,
    company_name: str,
    cities: list[str] | str | None = None,
    *,
    locations: list[dict] | None = None,
) -> dict:
    """Set or clear a company's office location tags."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")

    filename = COUNTRY_FILES.get(country_key)
    if not filename:
        raise ValueError(f"Unknown country: {country_key}")

    cleaned: list[dict] = []
    if locations is not None:
        seen: set[str] = set()
        for item in locations:
            if not isinstance(item, dict):
                continue
            loc = normalize_location(item.get("country", ""), item.get("city", ""))
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)
        cleaned.sort(key=lambda loc: (loc["country_label"], loc["city"].casefold()))
    elif isinstance(cities, str):
        city = (cities or "").strip()
        if city:
            loc = normalize_location(country_key, city)
            if loc:
                cleaned = [loc]
    elif isinstance(cities, list):
        seen = set()
        for item in cities:
            label = (item or "").strip()
            if not label:
                continue
            loc = normalize_location(country_key, label)
            if not loc or loc["key"] in seen:
                continue
            seen.add(loc["key"])
            cleaned.append(loc)
        cleaned.sort(key=lambda loc: (loc["country_label"], loc["city"].casefold()))

    with _file_lock:
        data = _load_country_data(country_key)
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        company["locations"] = cleaned
        sync_company_location_fields(company, catalog_country=country_key)
        company["updated"] = today()
        data["updated"] = today()
        _save_country_data(country_key, data)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": canonical_name,
        "city": company["city"],
        "cities": company.get("cities") or [],
        "locations": cleaned,
    }


def add_manual_jobs(
    country_key: str,
    company_name: str,
    jobs: list[dict],
) -> dict:
    """Append manually selected roles without removing existing matching jobs."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")

    filename = COUNTRY_FILES.get(country_key)
    if not filename:
        raise ValueError(f"Unknown country: {country_key}")

    ts = today()
    to_add: list[dict] = []
    for job in jobs:
        title = (job.get("title") or "").strip()
        url = normalize_job_url(job.get("url") or "")
        if not title or not url:
            continue
        to_add.append({
            "title": title,
            "url": url,
            "fetched": ts,
            "last_seen": ts,
        })

    if not to_add:
        raise ValueError("No valid jobs to add")

    with _file_lock:
        data = _load_country_data(country_key)
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        merged = list(company.get("matching_jobs") or [])
        existing_keys = {
            job_idempotency_key_for_job(j)
            for j in merged
            if job_idempotency_key_for_job(j)
        }
        new_count = 0
        for job in to_add:
            key = job_idempotency_key(job.get("url", ""))
            if not key:
                continue
            if key in existing_keys:
                continue
            stamp_job_identity(job)
            merged.append(job)
            existing_keys.add(key)
            new_count += 1

        company["matching_jobs"] = merged
        company["updated"] = ts
        data["updated"] = ts
        _save_country_data(country_key, data)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": canonical_name,
        "added": new_count,
        "total": len(merged),
    }


def set_company_fetch_problem(
    country_key: str,
    company_name: str,
    fetch_problem: bool,
    *,
    mark_fetch_ok: bool = False,
) -> dict:
    """Tag or untag a company as having fetch/scrape problems."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")

    filename = COUNTRY_FILES.get(country_key)
    if not filename:
        raise ValueError(f"Unknown country: {country_key}")

    with _file_lock:
        data = _load_country_data(country_key)
        company = find_company_in_data(data, company_name)
        if company is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = company.get("name", company_name)
        if fetch_problem:
            company["fetch_problem"] = True
            company["fetch_problem_date"] = today()
            company.pop("fetch_ok", None)
            company.pop("fetch_ok_date", None)
        else:
            company.pop("fetch_problem", None)
            company.pop("fetch_problem_date", None)
            if mark_fetch_ok:
                company["fetch_ok"] = True
                company["fetch_ok_date"] = today()
        _save_country_data(country_key, data)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "company": canonical_name,
        "fetch_problem": fetch_problem,
        "fetch_problem_date": company.get("fetch_problem_date", ""),
        "fetch_ok": bool(company.get("fetch_ok")),
        "fetch_ok_date": company.get("fetch_ok_date", ""),
    }


def set_company_fetch_ok(country_key: str, company_name: str) -> dict:
    """Mark a company as fetch-OK (clears fetch problem if set)."""
    return set_company_fetch_problem(
        country_key,
        company_name,
        False,
        mark_fetch_ok=True,
    )


def remove_company(country_key: str, company_name: str) -> dict:
    """Remove a company from the catalog and clear DB tracking."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Company name is required")

    filename = COUNTRY_FILES.get(country_key)
    if not filename:
        raise ValueError(f"Unknown country: {country_key}")

    target = company_name.lower()

    with _file_lock:
        data = _load_country_data(country_key)
        companies = data.get("companies", [])
        removed: dict | None = None
        kept: list[dict] = []
        for company in companies:
            if company.get("name", "").strip().lower() == target:
                if removed is not None:
                    raise LookupError(f"Duplicate company name: {company_name}")
                removed = company
            else:
                kept.append(company)

        if removed is None:
            raise LookupError(f"Company not found: {company_name}")

        canonical_name = removed.get("name", company_name)
        data["companies"] = kept
        data["updated"] = today()
        _save_country_data(country_key, data)

    clear_company_tracking(country_key, canonical_name)

    return {
        "country": country_key,
        "country_label": COUNTRY_LABELS.get(country_key, country_key),
        "file": filename,
        "company": canonical_name,
        "removed_jobs": len(removed.get("matching_jobs") or []),
    }
