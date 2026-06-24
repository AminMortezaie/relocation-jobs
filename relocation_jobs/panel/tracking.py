from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from relocation_jobs.core.job_identity import (
    job_idempotency_key,
    job_idempotency_key_for_job,
    normalize_job_url,
)
from relocation_jobs.core.location_tags import job_location_fields
from relocation_jobs.shared.coerce import as_bool


def tracking_key(country: str, company: str, url: str) -> tuple[str, str, str]:
    return (country, company, normalize_job_url(url))


def resolve_track(
    job_tracking: dict,
    *,
    country: str,
    company_name: str,
    job: dict,
) -> dict:
    direct_key = tracking_key(country, company_name, job.get("url", ""))
    direct = job_tracking.get(direct_key)
    job_key = job_idempotency_key_for_job(job)

    if direct is not None:
        merged = dict(direct)
    elif job_key:
        alias: dict | None = None
        catalog_norm = normalize_job_url(job.get("url", ""))
        for (t_country, t_company, t_url), track in job_tracking.items():
            if t_country != country or t_company != company_name:
                continue
            if job_idempotency_key(t_url) != job_key:
                continue
            if catalog_norm and normalize_job_url(t_url) == catalog_norm:
                alias = track
                break
            if alias is None:
                alias = track
        if alias is None:
            return {}
        merged = dict(alias)
    else:
        return {}

    seen_track: dict | None = None
    if job_key:
        for (t_country, t_company, t_url), track in job_tracking.items():
            if t_country != country or t_company != company_name:
                continue
            if job_idempotency_key(t_url) != job_key:
                continue
            if not as_bool(track.get("seen")):
                continue
            if not seen_track or (
                (track.get("seen_date") or "") and not (seen_track.get("seen_date") or "")
            ):
                seen_track = track
    if seen_track:
        merged["seen"] = True
        merged["seen_date"] = seen_track.get("seen_date", "") or ""
    return merged


def resolve_status_history(
    status_history: dict,
    *,
    country: str,
    company_name: str,
    job: dict,
) -> dict[str, list]:
    empty: dict[str, list] = {
        "applied": [], "rejected": [], "applied_events": [], "rejected_events": [],
    }
    direct_key = tracking_key(country, company_name, job.get("url", ""))
    direct = status_history.get(direct_key, empty)
    job_key = job_idempotency_key_for_job(job)
    if not job_key:
        return {
            "applied": list(direct["applied"]),
            "rejected": list(direct["rejected"]),
            "applied_events": list(direct.get("applied_events") or []),
            "rejected_events": list(direct.get("rejected_events") or []),
        }

    applied_dates = list(direct["applied"])
    rejected_dates = list(direct["rejected"])
    applied_events = list(direct.get("applied_events") or [])
    rejected_events = list(direct.get("rejected_events") or [])
    seen_applied = {
        (e.get("at") or e.get("date") or "").strip()
        for e in applied_events if (e.get("at") or e.get("date") or "").strip()
    }
    seen_rejected = {
        (e.get("at") or e.get("date") or "").strip()
        for e in rejected_events if (e.get("at") or e.get("date") or "").strip()
    }
    for (t_country, t_company, t_url), hist in status_history.items():
        if t_country != country or t_company != company_name:
            continue
        if job_idempotency_key(t_url) != job_key:
            continue
        if tracking_key(t_country, t_company, t_url) == direct_key:
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


def catalog_not_for_me(job: dict) -> bool:
    return bool(job.get("not_for_me"))


def _display_status_date(track_date: str, history_dates: list[str]) -> str:
    candidates = [(d or "").strip() for d in (history_dates or []) if (d or "").strip()]
    td = (track_date or "").strip()
    if td:
        candidates.append(td)
    return max(candidates) if candidates else ""


def _latest_applied_at(hist: dict, track: dict | None = None, *, applied: bool = False) -> str:
    events = hist.get("applied_events") or []
    ats = [(e.get("at") or "").strip() for e in events if (e.get("at") or "").strip()]
    if ats:
        return max(ats)
    if applied and track:
        return (track.get("updated_at") or "").strip()
    return ""


def _status_history(
    status_history: dict | None,
    *,
    country_key: str,
    company_name: str,
    job: dict,
) -> dict:
    if status_history is None:
        return {"applied": [], "rejected": [], "applied_events": [], "rejected_events": []}
    return resolve_status_history(
        status_history,
        country=country_key,
        company_name=company_name,
        job=job,
    )


def tracked_job_dict(
    track: dict,
    *,
    company_name: str,
    company: dict,
    country_key: str,
    country_label: str,
    status_history: dict | None = None,
) -> dict:
    url = track.get("job_url", "")
    title = (track.get("job_title") or "").strip() or _title_from_tracked_url(url)
    applied = bool(track.get("applied"))
    rejected = as_bool(track.get("rejected"))
    hist = _status_history(
        status_history,
        country_key=country_key,
        company_name=company_name,
        job={"url": url},
    )
    return {
        "title": title,
        "url": url,
        "idempotency_key": job_idempotency_key(url),
        "fetched": "",
        "last_seen": "",
        "visa_sponsorship": None,
        "applied": applied,
        "applied_date": _display_status_date(track.get("applied_date", "") if applied else "", hist["applied"]),
        "applied_at": _latest_applied_at(hist, track, applied=applied),
        "applied_history": hist["applied"],
        "applied_events": hist.get("applied_events") or [],
        "not_for_me": False,
        "not_for_me_date": "",
        "rejected": rejected,
        "rejected_date": _display_status_date(track.get("rejected_date", "") if rejected else "", hist["rejected"]),
        "rejected_history": hist["rejected"],
        "looking_to_apply": bool(track.get("looking_to_apply")),
        "looking_to_apply_date": track.get("looking_to_apply_date", "") or "",
        "seen": as_bool(track.get("seen")),
        "seen_date": track.get("seen_date", "") or "",
        "ats_score": _ats_score_value(track.get("ats_score")),
        "tracked_only": True,
        "company": company_name,
        "city": company.get("city", ""),
        "size": company.get("size", ""),
        "country": country_key,
        "country_label": country_label,
        "careers_url": company.get("careers_url", ""),
        "ats_type": company.get("ats_type", ""),
    }


def job_dict(
    job: dict,
    *,
    company_name: str,
    company: dict,
    country_key: str,
    country_label: str,
    job_tracking: dict | None = None,
    status_history: dict | None = None,
) -> dict:
    url = job.get("url", "")
    track = (
        resolve_track(job_tracking, country=country_key, company_name=company_name, job=job)
        if job_tracking is not None
        else {}
    )
    logged_in = job_tracking is not None
    applied = bool(track.get("applied")) if logged_in else bool(job.get("applied"))
    not_for_me = bool(track.get("not_for_me")) if logged_in else bool(job.get("not_for_me"))
    rejected = as_bool(track.get("rejected")) if logged_in else as_bool(job.get("rejected"))
    waiting_referral = bool(track.get("waiting_referral")) if logged_in else bool(job.get("waiting_referral"))
    hist = _status_history(status_history, country_key=country_key, company_name=company_name, job=job)
    track_applied_date = (track.get("applied_date", "") if logged_in else job.get("applied_date", "")) if applied else ""
    track_rejected_date = (track.get("rejected_date", "") if logged_in else job.get("rejected_date", "")) if rejected else ""
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
        "not_for_me_date": (track.get("not_for_me_date", "") if logged_in else job.get("not_for_me_date", "")) if not_for_me else "",
        "not_for_me_reason": (track.get("not_for_me_reason", "") if logged_in else job.get("not_for_me_reason", "")) if not_for_me else "",
        "rejected": rejected,
        "rejected_date": _display_status_date(track_rejected_date, hist["rejected"]),
        "rejected_history": hist["rejected"],
        "waiting_referral": waiting_referral,
        "waiting_referral_date": (track.get("waiting_referral_date", "") if logged_in else job.get("waiting_referral_date", "")) if waiting_referral else "",
        "referral_linkedin_url": (track.get("referral_linkedin_url", "") if logged_in else job.get("referral_linkedin_url", "")) if waiting_referral else "",
        "ats_score": _ats_score_value(track.get("ats_score")) if logged_in else _ats_score_value(job.get("ats_score")),
        "seen": as_bool(track.get("seen")) if logged_in else as_bool(job.get("seen")),
        "seen_date": (track.get("seen_date", "") if logged_in else job.get("seen_date", "")) or "",
        "looking_to_apply": bool(track.get("looking_to_apply")) if logged_in else bool(job.get("looking_to_apply")),
        "looking_to_apply_date": (track.get("looking_to_apply_date", "") if logged_in else job.get("looking_to_apply_date", "")) or "",
        "company": company_name,
        "city": company.get("city", ""),
        "size": company.get("size", ""),
        "country": country_key,
        "country_label": country_label,
        "careers_url": company.get("careers_url", ""),
        "ats_type": company.get("ats_type", ""),
    }
