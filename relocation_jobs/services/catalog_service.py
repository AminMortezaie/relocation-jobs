"""Catalog read and aggregation service.

Owns flatten_companies, compute_stats, location queries and the
catalog data load/save helpers. No raw SQL — all DB access through db/.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

from relocation_jobs.catalog_db import (
    country_key_from_filename,
    load_country_catalog,
    save_country_catalog,
)
from relocation_jobs.db import (
    count_jobs_applied_db,
    count_jobs_applied_today_db,
    list_fetch_runs,
    list_jobs_applied_today_db,
    load_company_tracking,
    load_job_status_history,
    load_job_tracking,
)
from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
)
from relocation_jobs.core.location_tags import (
    COUNTRY_LABELS,
    SUGGESTED_CITIES,
    company_matches_location_filter,
    company_visible_for_country_filter,
    job_fails_office_location_gate,
    job_location_fields,
    normalize_country_key,
    normalize_location,
    normalize_locations,
    picker_cities_for_country,
    sync_company_location_fields,
)
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, SUPPORTED_COUNTRIES

from relocation_jobs.core.ats_constants import ATS_TYPE_CHOICES


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def today() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_ts_for_sort(ts: str) -> str:
    ts = (ts or "").strip()
    if not ts:
        return "0000-00-00T00:00:00"
    if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
        return f"{ts}T00:00:00"
    return ts.replace("Z", "+00:00")


def _job_activity_ts(job: dict) -> str:
    return (job.get("fetched") or job.get("last_seen") or "").strip()


def _company_activity_ts(company: dict, stored_jobs: list[dict]) -> str:
    updated = (company.get("updated") or "").strip()
    if updated:
        return updated
    job_ts = [_job_activity_ts(j) for j in stored_jobs if _job_activity_ts(j)]
    if job_ts:
        return max(job_ts, key=_normalize_ts_for_sort)
    return (company.get("added") or "").strip()


# ---------------------------------------------------------------------------
# Country data loading / saving
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tracking resolution helpers
# ---------------------------------------------------------------------------

def _tracking_key(country: str, company: str, url: str) -> tuple[str, str, str]:
    return (country, company, normalize_job_url(url))


def _tracking_bool(value) -> bool:
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
    empty: dict[str, list] = {
        "applied": [], "rejected": [], "applied_events": [], "rejected_events": []
    }
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
    seen_applied: set[str] = {
        (e.get("at") or e.get("date") or "").strip()
        for e in applied_events if (e.get("at") or e.get("date") or "").strip()
    }
    seen_rejected: set[str] = {
        (e.get("at") or e.get("date") or "").strip()
        for e in rejected_events if (e.get("at") or e.get("date") or "").strip()
    }
    for (t_country, t_company, t_url), hist in status_history.items():
        if t_country != country or t_company != company_name:
            continue
        if job_idempotency_key(t_url) != job_key:
            continue
        if _tracking_key(t_country, t_company, t_url) == direct_key:
            continue
        for d in hist.get("applied") or []:
            if d and d not in applied_dates:
                applied_dates.append(d)
        for d in hist.get("rejected") or []:
            if d and d not in rejected_dates:
                rejected_dates.append(d)
        for event in hist.get("applied_events") or []:
            marker = (event.get("at") or event.get("date") or "").strip()
            if marker and marker not in seen_applied:
                seen_applied.add(marker)
                applied_events.append(dict(event))
        for event in hist.get("rejected_events") or []:
            marker = (event.get("at") or event.get("date") or "").strip()
            if marker and marker not in seen_rejected:
                seen_rejected.add(marker)
                rejected_events.append(dict(event))
    applied_dates.sort()
    rejected_dates.sort()
    applied_events.sort(key=lambda e: (e.get("at") or e.get("date") or ""))
    rejected_events.sort(key=lambda e: (e.get("at") or e.get("date") or ""))
    return {
        "applied": applied_dates,
        "rejected": rejected_dates,
        "applied_events": applied_events,
        "rejected_events": rejected_events,
    }


def _latest_applied_at(hist: dict, track: dict | None = None, *, applied: bool = False) -> str:
    events = hist.get("applied_events") or []
    ats = [(e.get("at") or "").strip() for e in events if (e.get("at") or "").strip()]
    if ats:
        return max(ats)
    if applied and track:
        return (track.get("updated_at") or "").strip()
    return ""


def _latest_status_date(dates: list[str]) -> str:
    clean = [(d or "").strip() for d in dates if (d or "").strip()]
    return max(clean) if clean else ""


def _display_status_date(track_date: str, history_dates: list[str]) -> str:
    candidates = [(d or "").strip() for d in (history_dates or []) if (d or "").strip()]
    td = (track_date or "").strip()
    if td:
        candidates.append(td)
    return max(candidates) if candidates else ""


def _ats_score_value(raw) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        score = int(raw)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 100 else None


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


def _job_not_for_me(job: dict) -> bool:
    return bool(job.get("not_for_me"))


# ---------------------------------------------------------------------------
# Job dict builders
# ---------------------------------------------------------------------------

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
        _resolve_status_history(status_history, country=key, company_name=company_name, job={"url": url})
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
        (track.get("not_for_me_date", "") if job_tracking is not None else job.get("not_for_me_date", ""))
        if not_for_me else ""
    )
    not_for_me_reason = (
        (track.get("not_for_me_reason", "") if job_tracking is not None else job.get("not_for_me_reason", ""))
        if not_for_me else ""
    )
    rejected = (
        _tracking_bool(track.get("rejected")) if job_tracking is not None
        else _tracking_bool(job.get("rejected"))
    )
    waiting_referral = (
        bool(track.get("waiting_referral")) if job_tracking is not None
        else bool(job.get("waiting_referral"))
    )
    waiting_referral_date = (
        (track.get("waiting_referral_date", "") if job_tracking is not None
         else job.get("waiting_referral_date", ""))
        if waiting_referral else ""
    )
    referral_linkedin_url = (
        (track.get("referral_linkedin_url", "") if job_tracking is not None
         else job.get("referral_linkedin_url", ""))
        if waiting_referral else ""
    )
    ats_score = (
        _ats_score_value(track.get("ats_score")) if job_tracking is not None
        else _ats_score_value(job.get("ats_score"))
    )
    seen = (
        _tracking_bool(track.get("seen")) if job_tracking is not None
        else _tracking_bool(job.get("seen"))
    )
    seen_date = track.get("seen_date", "") if job_tracking is not None else job.get("seen_date", "")
    looking_to_apply = (
        bool(track.get("looking_to_apply")) if job_tracking is not None
        else bool(job.get("looking_to_apply"))
    )
    looking_to_apply_date = (
        track.get("looking_to_apply_date", "") if job_tracking is not None
        else job.get("looking_to_apply_date", "")
    )
    hist = (
        _resolve_status_history(status_history, country=key, company_name=company_name, job=job)
        if status_history is not None
        else {"applied": [], "rejected": []}
    )
    track_applied_date = (
        (track.get("applied_date", "") if job_tracking is not None else job.get("applied_date", ""))
        if applied else ""
    )
    track_rejected_date = (
        (track.get("rejected_date", "") if job_tracking is not None else job.get("rejected_date", ""))
        if rejected else ""
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
    listed_urls = {normalize_job_url(j.get("url", "")) for j in jobs}
    listed_urls.update(normalize_job_url(j.get("url", "")) for j in rejected_jobs)
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


# ---------------------------------------------------------------------------
# Main public query functions
# ---------------------------------------------------------------------------

def _company_ats_type(company: dict) -> str:
    return (company.get("ats_type") or "").strip() or "generic"


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
    ats_type: str | None = None,
    user_id: int | None = None,
) -> tuple[list[dict], list[dict], int]:
    companies_out: list[dict] = []
    file_meta: list[dict] = []
    fetch_problem_count = 0

    job_tracking = load_job_tracking(user_id) if user_id else {}
    company_tracking = load_company_tracking(user_id) if user_id else {}
    status_history = load_job_status_history(user_id) if user_id else {}

    keys = [country_key] if country_key and country_key != "all" else sorted(SUPPORTED_COUNTRIES)
    company_keys = sorted(SUPPORTED_COUNTRIES)

    location_filter = (location or city or "").strip() or None
    country_cache: dict[str, dict] = {}

    for key in keys:
        filename = COUNTRY_ARCHIVE_FILENAMES.get(key)
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
        filename = COUNTRY_ARCHIVE_FILENAMES.get(key)
        if not filename:
            continue
        data = _load_country_data(key, cache=country_cache)
        if not data.get("companies") and not data.get("source"):
            continue
        label = COUNTRY_LABELS.get(key, key)

        for company in data.get("companies", []):
            company_name = company.get("name", "")
            if country_key and country_key != "all":
                if not company_visible_for_country_filter(company, country_key, catalog_country=key):
                    continue
            if location_filter and not company_matches_location_filter(company, location_filter, catalog_country=key):
                continue
            if ats_type and _company_ats_type(company) != ats_type:
                continue
            if company.get("fetch_problem"):
                fetch_problem_count += 1

            if user_id:
                company_applied, company_applied_date, _positions, company_applied_at = (
                    _derive_company_applied(key, company_name, company.get("matching_jobs") or [], job_tracking)
                )
            else:
                company_applied = bool(company.get("company_applied"))
                company_applied_date = company.get("company_applied_date", "") if company_applied else ""
                _positions = 0
                company_applied_at = ""

            company_track = company_tracking.get((key, company_name), {})
            awaiting_response = bool(company_track.get("awaiting_response")) if user_id else False
            awaiting_response_date = (
                (company_track.get("awaiting_response_date") or "").strip()
                if awaiting_response and user_id else ""
            )

            if hide_applied and company_applied:
                continue
            if fetch_ok_only and not (company.get("fetch_ok") and not company.get("fetch_problem")):
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
                track = _resolve_track(job_tracking, country=key, company_name=company_name, job=job)
                if user_id:
                    if track.get("not_for_me"):
                        positions_not_for_me += 1
                        not_for_me_jobs.append(_job_dict(
                            job, company_name=company_name, company=company,
                            key=key, label=label, job_tracking=job_tracking, status_history=status_history,
                        ))
                        continue
                elif _job_not_for_me(job):
                    positions_not_for_me += 1
                    not_for_me_jobs.append(_job_dict(
                        job, company_name=company_name, company=company,
                        key=key, label=label, job_tracking=None,
                    ))
                    continue

                fails_gate, _ = job_fails_office_location_gate(job, company, catalog_country=key)
                if fails_gate:
                    positions_not_for_me += 1
                    wrong_entry = _job_dict(
                        job, company_name=company_name, company=company,
                        key=key, label=label,
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
                    job, company_name=company_name, company=company,
                    key=key, label=label,
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
                    jobs, rejected_jobs,
                    key=key, company_name=company_name, company=company, label=label,
                    job_tracking=job_tracking, status_history=status_history,
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
            visible_ts = [_job_activity_ts(j) for j in jobs if _job_activity_ts(j)]
            latest_fetch = max(visible_ts, default="") or sort_ts
            positions_applied = sum(1 for j in jobs if j.get("applied"))
            positions_rejected = len(rejected_jobs)
            positions_applied_all = _positions if user_id else positions_applied

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
                "newest_job_fetched": sort_ts,
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
    companies, file_meta, _ = flatten_companies(
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
        1 for c in companies for j in c.get("jobs", []) if j.get("visa_sponsorship") is True
    )
    positions_applied = (
        count_jobs_applied_db(user_id, country=country_key)
        if user_id
        else sum(c.get("positions_applied_all", c.get("positions_applied", 0)) for c in companies)
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
        count_jobs_applied_today_db(user_id, country=country_key, timezone_name=timezone_name)
        if user_id else 0
    )
    applied_today_jobs = (
        list_jobs_applied_today_db(user_id, country=country_key, timezone_name=timezone_name)
        if user_id else []
    )
    recent_fetch_runs = (
        list_fetch_runs(user_id, country=country_key, limit=5)
        if user_id else []
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


# ---------------------------------------------------------------------------
# Location queries
# ---------------------------------------------------------------------------

def list_company_locations(
    country_key: str | None = None,
    *,
    for_picker: bool = False,
) -> list[dict]:
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
        for key in SUPPORTED_COUNTRIES:
            for city in picker_cities_for_country(key):
                add(key, city)

    for key in sorted(SUPPORTED_COUNTRIES):
        data = _load_country_data(key)
        for company in data.get("companies") or []:
            locations = normalize_locations(
                company.get("locations"),
                catalog_country=key,
                legacy_cities=company.get("cities") if isinstance(company.get("cities"), list) else None,
                legacy_city=company.get("city", ""),
            )
            for loc in locations:
                add(loc["country"], loc["city"])

    return sorted(keyed.values(), key=lambda loc: (loc["country_label"], loc["city"].casefold()))


def list_company_cities(country_key: str | None = None) -> list[str]:
    return [loc["city"] for loc in list_company_locations(country_key)]


def list_ats_types() -> list[dict]:
    return [{"id": key, "label": label} for key, label in ATS_TYPE_CHOICES]


def parse_company_cities(company: dict, *, catalog_country: str = "") -> list[str]:
    sync_company_location_fields(company, catalog_country=catalog_country)
    return company.get("cities") or []

