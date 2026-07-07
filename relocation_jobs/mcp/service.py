from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from relocation_jobs.catalog.repo import (
    get_company,
    get_job_by_idempotency_key,
    get_job_by_url,
    update_job_description_text,
    update_matching_job_fields,
)
from relocation_jobs.companies.service import add_company as catalog_add_company
from relocation_jobs.companies.service import add_manual_jobs as catalog_add_manual_jobs
from relocation_jobs.companies.service import list_ats_types as catalog_list_ats_types
from relocation_jobs.core.location_tags import (
    COUNTRY_LABELS,
    add_custom_country,
    all_country_labels,
    ensure_country_key,
)
from relocation_jobs.core.paths import supported_countries
from relocation_jobs.scrape.descriptions import format_job_description
from relocation_jobs.scrape.job_text import fetch_job_description
from relocation_jobs.core.db import _normalize_url
from relocation_jobs.core.job_identity import job_idempotency_key, normalize_job_url
from relocation_jobs.db.users import get_user_by_username
from relocation_jobs.mcp import repo, render, validate
from relocation_jobs.mcp.names import application_pdf_filename, master_pdf_filename
from relocation_jobs.mcp.types import (
    AddCompanyResult,
    AddPositionResult,
    ApplicationProfile,
    ApplicationQueueItem,
    ApplicationTexDetail,
    AtsTypeOption,
    CompanyApplicationsResponse,
    CompanyPositionApplication,
    JobContext,
    MasterResumeSummary,
    PositionDescription,
    RenderResult,
    SavePositionDescriptionResult,
    SupportedCountry,
    UpdatePositionResult,
    ValidationResult,
)
from relocation_jobs.core.location_tags import job_fails_office_location_gate
from relocation_jobs.panel.tracking import resolve_track
from relocation_jobs.positions.service import set_job_applied
from relocation_jobs.positions.state import position_view_from_row
from relocation_jobs.positions.types import PositionBucket
from relocation_jobs.shared.timestamps import job_fetched_ts, normalize_posted_at
from relocation_jobs.users.repo import load_job_tracking


_MIN_JD_CHARS = 80
_NON_FETCHABLE_POSTING_HOSTS = frozenset({
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
})


def _posting_host(url: str) -> str:
    return (urlparse(normalize_job_url(url)).hostname or "").lower()


def _non_fetchable_posting_url(url: str) -> bool:
    host = _posting_host(url)
    return host in _NON_FETCHABLE_POSTING_HOSTS


def _merge_job_description(existing: str, new: str) -> str:
    current = (existing or "").strip()
    incoming = (new or "").strip()
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming == current:
        return current
    if incoming in current:
        return current
    if current in incoming:
        return incoming
    return f"{current}\n\n---\n\n{incoming}"


def _persist_job_description(
    idempotency_key: str,
    description_text: str,
    *,
    existing: str = "",
    overwrite: bool = False,
) -> bool:
    key = (idempotency_key or "").strip()
    incoming = (description_text or "").strip()
    if overwrite:
        if incoming == (existing or "").strip():
            return False
        return update_job_description_text(key, incoming)
    merged = _merge_job_description(existing, description_text)
    if not merged or merged == (existing or "").strip():
        return False
    return update_job_description_text(key, merged)


def _resolve_catalog_position(
    country_key: str,
    company: str,
    url: str,
) -> tuple[str, dict]:
    company_name = resolve_company_for_workspace(country_key, company)
    cleaned_url = (url or "").strip()
    job = get_job_by_url(
        cleaned_url,
        company_name=company_name,
        country_key=country_key,
    )
    if job is None:
        raise LookupError(f"Position not found: {cleaned_url}")
    return company_name, job


def _position_result_from_job(
    *,
    country_key: str,
    company_name: str,
    job: dict,
    updated_fields: list[str] | None = None,
) -> UpdatePositionResult:
    desc_fields = _job_description_fields(job)
    has_description = bool(desc_fields.get("has_description"))
    canonical_url = (job.get("url") or "").strip()
    slug = repo.company_slug(company_name)
    idem_key = (job.get("idempotency_key") or "").strip()
    return UpdatePositionResult(
        country=country_key,
        company=company_name,
        company_slug=slug,
        title=(job.get("title") or "").strip(),
        url=canonical_url,
        idempotency_key=idem_key,
        location=(job.get("location") or "").strip(),
        has_description=has_description,
        needs_description=not has_description,
        description_chars=len((job.get("description_text") or "")),
        updated_fields=updated_fields or [],
        posted_at=job_fetched_ts(job),
        workspace_path=f"/company/{country_key}/{slug}",
    )


def _validate_manual_jd(description_text: str, *, url: str) -> str:
    cleaned = (description_text or "").strip()
    if _non_fetchable_posting_url(url):
        if len(cleaned) < _MIN_JD_CHARS:
            raise ValueError(
                "description_text is required for LinkedIn and similar postings — "
                f"paste the full job description (at least {_MIN_JD_CHARS} characters)"
            )
    return cleaned


def _validate_posted_at(posted_at: str, *, url: str) -> str:
    cleaned = (posted_at or "").strip()
    if _non_fetchable_posting_url(url):
        if not cleaned:
            raise ValueError(
                "posted_at is required for LinkedIn and similar postings — "
                "use the posting date from the listing (YYYY-MM-DD or ISO datetime)"
            )
        return normalize_posted_at(cleaned)
    if not cleaned:
        return ""
    return normalize_posted_at(cleaned)


def _apply_posted_at_to_job(job: dict, posted_at: str) -> None:
    if not posted_at:
        return
    job["posted_at"] = posted_at
    job["fetched"] = posted_at
    job["last_seen"] = posted_at


def resolve_user_id() -> int:
    raw_id = (os.environ.get("MCP_USER_ID") or "").strip()
    if raw_id:
        return int(raw_id)
    username = (os.environ.get("MCP_USERNAME") or "admin").strip() or "admin"
    user = get_user_by_username(username)
    if user is None:
        raise LookupError(f"MCP user not found: {username}")
    return int(user["id"])


def _tracking_row(
    tracking: dict[tuple[str, str, str], dict],
    country: str,
    company: str,
    job_url: str,
) -> dict:
    key = (country, company, _normalize_url(job_url))
    return tracking.get(key, {})


def _application_state(user_id: int, idempotency_key: str) -> dict:
    row = repo.get_application(user_id, idempotency_key) or {}
    return {
        "has_tex": bool((row.get("tailored_tex") or "").strip()),
        "has_pdf": bool(row.get("pdf_bytes")),
        "master_slug": (row.get("master_resume_slug") or "").strip(),
    }


def _application_pdf_filename(user_id: int, company: str) -> str:
    profile = get_application_profile(user_id=user_id)
    return application_pdf_filename(profile.full_name, company)


def _master_pdf_filename(user_id: int, slug: str) -> str:
    profile = get_application_profile(user_id=user_id)
    return master_pdf_filename(profile.full_name, slug)


def _resolve_master_slug(
    user_id: int,
    idempotency_key: str,
    slug: str | None,
) -> str:
    if slug and slug.strip():
        return repo.normalize_master_resume_slug(slug)
    stored = _application_state(user_id, idempotency_key)["master_slug"]
    if stored:
        return stored
    raise LookupError(
        "master_resume_slug is required (e.g. go, java, fullstack). "
        "Pass it to save_tailored_tex / validate_tex, or save tailored tex first."
    )


def _job_description_fields(job: dict) -> dict[str, str | bool]:
    raw = (job.get("description_text") or "").strip()
    readable, display_html = format_job_description(raw)
    has = bool(readable)
    return {
        "description_text": readable,
        "description_html": display_html,
        "has_description": has,
        "needs_fetch": not has,
    }


def get_job_context(
    country: str,
    company: str,
    url: str,
    *,
    user_id: int | None = None,
) -> JobContext:
    uid = user_id if user_id is not None else resolve_user_id()
    country_key = country.strip().lower()
    company_name = resolve_company_for_workspace(country_key, company)
    job = get_job_by_url(url, company_name=company_name, country_key=country_key)
    if job is None:
        raise LookupError(f"Job not found: {company} — {url[:120]}")

    company_row = get_company(country_key, company_name) or {}
    catalog_url = (job.get("url") or url).strip()
    idem_key = (job.get("idempotency_key") or "").strip() or job_idempotency_key(catalog_url)
    tracking = load_job_tracking(uid, country=country_key)
    row = _tracking_row(tracking, country_key, company_name, catalog_url)
    app_state = _application_state(uid, idem_key)
    pinned = bool(row.get("pinned"))
    looking_to_apply = bool(row.get("looking_to_apply"))
    description = _job_description_fields(job)

    return JobContext(
        country=country_key,
        company=company_name,
        url=catalog_url,
        title=(job.get("title") or "").strip(),
        idempotency_key=idem_key,
        ats_type=(company_row.get("ats_type") or "").strip(),
        ats_url=(company_row.get("ats_url") or "").strip(),
        location=(job.get("location") or "").strip(),
        visa_sponsorship=job.get("visa_sponsorship"),
        applied=bool(row.get("applied")),
        rejected=bool(row.get("rejected")),
        looking_to_apply=looking_to_apply,
        pinned=pinned,
        in_application_queue=pinned or looking_to_apply,
        can_save_tailored_tex=True,
        ats_score=row.get("ats_score"),
        master_resume_slug=app_state["master_slug"],
        has_tailored_tex=app_state["has_tex"],
        has_pdf=app_state["has_pdf"],
        pdf_filename=_application_pdf_filename(uid, company_name),
        description_text=str(description["description_text"]),
        has_description=bool(description["has_description"]),
        needs_fetch=bool(description["needs_fetch"]),
        description_html=str(description.get("description_html") or ""),
        posted_at=job_fetched_ts(job),
    )


def list_application_queue(
    *,
    user_id: int | None = None,
    country: str | None = None,
) -> list[ApplicationQueueItem]:
    uid = user_id if user_id is not None else resolve_user_id()
    scope = (country or "").strip().lower() or None
    tracking = load_job_tracking(uid, country=scope)
    items: list[ApplicationQueueItem] = []

    for (country_key, company_name, job_url), row in tracking.items():
        if not row.get("pinned") and not row.get("looking_to_apply"):
            continue
        job = get_job_by_url(
            job_url,
            company_name=company_name,
            country_key=country_key,
        )
        catalog_url = (job or {}).get("url") or job_url
        idem_key = (
            (job or {}).get("idempotency_key") or ""
        ).strip() or job_idempotency_key(catalog_url)
        items.append(ApplicationQueueItem(
            country=country_key,
            company=company_name,
            url=catalog_url,
            title=((job or {}).get("title") or row.get("job_title") or "").strip(),
            idempotency_key=idem_key,
            pinned=bool(row.get("pinned")),
            looking_to_apply=bool(row.get("looking_to_apply")),
            ats_score=row.get("ats_score"),
        ))

    items.sort(key=lambda item: (not item.pinned, not item.looking_to_apply, item.company.lower()))
    return items


def resolve_company_for_workspace(
    country: str,
    company_or_slug: str,
) -> str:
    country_key = country.strip().lower()
    raw = (company_or_slug or "").strip()
    if not raw:
        raise LookupError("company is required")
    company_row = get_company(country_key, raw)
    if company_row is not None:
        return (company_row.get("name") or raw).strip()
    resolved = repo.resolve_company_name_by_slug(country_key, raw)
    if resolved is None:
        raise LookupError(f"Company not found: {company_or_slug}")
    return resolved


def list_company_applications(
    country: str,
    company: str,
    *,
    user_id: int | None = None,
) -> CompanyApplicationsResponse:
    uid = user_id if user_id is not None else resolve_user_id()
    country_key = country.strip().lower()
    company_name = resolve_company_for_workspace(country_key, company)
    company_row = get_company(country_key, company_name)
    if company_row is None:
        raise LookupError(f"Company not found: {company}")

    tracking = load_job_tracking(uid, country=country_key)
    app_rows = repo.list_applications_for_company(uid, country_key, company_name)
    profile = get_application_profile(user_id=uid)
    app_by_key = {
        (row.get("idempotency_key") or "").strip(): row
        for row in app_rows
        if (row.get("idempotency_key") or "").strip()
    }

    positions: list[CompanyPositionApplication] = []
    for job in company_row.get("matching_jobs") or []:
        track = resolve_track(
            tracking,
            country=country_key,
            company_name=company_name,
            job=job,
        )
        wrong_location, _ = job_fails_office_location_gate(
            job, company_row, catalog_country=country_key,
        )
        if position_view_from_row(track, wrong_location=wrong_location).bucket == PositionBucket.NOT_FOR_ME:
            continue
        catalog_url = (job.get("url") or "").strip()
        idem_key = (
            (job.get("idempotency_key") or "").strip()
            or job_idempotency_key(catalog_url)
        )
        row = track
        app = app_by_key.get(idem_key, {})
        positions.append(CompanyPositionApplication(
            title=(job.get("title") or "").strip(),
            url=catalog_url,
            idempotency_key=idem_key,
            location=(job.get("location") or "").strip(),
            applied=bool(row.get("applied")),
            rejected=bool(row.get("rejected")),
            looking_to_apply=bool(row.get("looking_to_apply")),
            pinned=bool(row.get("pinned")),
            ats_score=row.get("ats_score"),
            has_tailored_tex=bool((app.get("tailored_tex") or "").strip()),
            has_pdf=bool(app.get("pdf_bytes")),
            master_resume_slug=(app.get("master_resume_slug") or "").strip(),
            tailored_tex_updated_at=(app.get("tailored_tex_updated_at") or "").strip(),
            pdf_updated_at=(app.get("pdf_updated_at") or "").strip(),
            pdf_filename=application_pdf_filename(profile.full_name, company_name),
            has_description=bool(_job_description_fields(job)["has_description"]),
        ))

    positions.sort(key=lambda item: (not item.pinned, not item.looking_to_apply, item.title.lower()))
    return CompanyApplicationsResponse(
        country=country_key,
        company=company_name,
        company_slug=repo.company_slug(company_name),
        positions=positions,
    )


def get_position_description(idempotency_key: str) -> PositionDescription:
    key = (idempotency_key or "").strip()
    if not key:
        raise LookupError("idempotency_key is required")
    job = get_job_by_idempotency_key(key)
    if job is None:
        raise LookupError(f"Position not found: {key}")
    description = _job_description_fields(job)
    return PositionDescription(
        idempotency_key=key,
        country=(job.get("country") or "").strip(),
        company=(job.get("company_name") or "").strip(),
        url=(job.get("url") or "").strip(),
        title=(job.get("title") or "").strip(),
        description_text=str(description["description_text"]),
        has_description=bool(description["has_description"]),
        needs_fetch=bool(description["needs_fetch"]),
        description_html=str(description.get("description_html") or ""),
    )


def fetch_and_store_position_description(idempotency_key: str) -> PositionDescription:
    key = (idempotency_key or "").strip()
    if not key:
        raise LookupError("idempotency_key is required")
    job = get_job_by_idempotency_key(key)
    if job is None:
        raise LookupError(f"Position not found: {key}")
    url = (job.get("url") or "").strip()
    if not url:
        raise ValueError("Position has no job URL")
    country_key = (job.get("country") or "").strip().lower()
    company_name = (job.get("company_name") or "").strip()
    company_row = get_company(country_key, company_name) or {}
    ats_type = (company_row.get("ats_type") or "").strip() or None
    text = fetch_job_description(url, ats_type)
    stripped = (text or "").strip()
    if stripped and not update_job_description_text(key, stripped):
        raise LookupError(f"Position not found: {key}")
    return get_position_description(key)


def get_application_detail(
    idempotency_key: str,
    *,
    user_id: int | None = None,
) -> JobContext:
    uid = user_id if user_id is not None else resolve_user_id()
    row = repo.get_application(uid, idempotency_key)
    if row is None:
        raise LookupError(f"Application not found: {idempotency_key}")
    return get_job_context(
        row["country"],
        row["company_name"],
        row["job_url"],
        user_id=uid,
    )


def read_application_tex(
    idempotency_key: str,
    *,
    user_id: int | None = None,
) -> ApplicationTexDetail:
    uid = user_id if user_id is not None else resolve_user_id()
    row = repo.get_application(uid, idempotency_key)
    if row is None:
        raise LookupError(f"Application not found: {idempotency_key}")
    content = repo.read_tailored_tex(uid, idempotency_key)
    ctx = get_job_context(
        row["country"],
        row["company_name"],
        row["job_url"],
        user_id=uid,
    )
    return ApplicationTexDetail(
        idempotency_key=idempotency_key,
        country=ctx.country,
        company=ctx.company,
        url=ctx.url,
        title=ctx.title,
        content=content,
        master_resume_slug=ctx.master_resume_slug,
        updated_at=(row.get("tailored_tex_updated_at") or "").strip(),
    )


def save_application_tex(
    idempotency_key: str,
    content: str,
    *,
    user_id: int | None = None,
) -> dict:
    uid = user_id if user_id is not None else resolve_user_id()
    row = repo.get_application(uid, idempotency_key)
    if row is None:
        raise LookupError(f"Application not found: {idempotency_key}")
    if not content.strip():
        raise ValueError("LaTeX content cannot be empty")
    master_slug = (row.get("master_resume_slug") or "").strip()
    if not master_slug:
        raise ValueError("Application has no master resume slug")
    saved = repo.save_tailored_tex(
        uid,
        idempotency_key,
        content,
        country=row["country"],
        company=row["company_name"],
        url=row["job_url"],
        master_resume_slug=master_slug,
    )
    return {
        "ok": True,
        "idempotency_key": idempotency_key,
        "updated_at": saved["updated_at"],
    }


def read_application_pdf(
    idempotency_key: str,
    *,
    user_id: int | None = None,
) -> bytes:
    uid = user_id if user_id is not None else resolve_user_id()
    return repo.read_pdf_bytes(uid, idempotency_key)


def read_application_pdf_download(
    idempotency_key: str,
    *,
    user_id: int | None = None,
) -> tuple[bytes, str]:
    uid = user_id if user_id is not None else resolve_user_id()
    row = repo.get_application(uid, idempotency_key)
    if row is None:
        raise LookupError(f"Application not found: {idempotency_key}")
    pdf_bytes = repo.read_pdf_bytes(uid, idempotency_key)
    filename = _application_pdf_filename(uid, row["company_name"])
    return pdf_bytes, filename


def render_application_pdf(
    idempotency_key: str,
    *,
    user_id: int | None = None,
) -> RenderResult:
    uid = user_id if user_id is not None else resolve_user_id()
    row = repo.get_application(uid, idempotency_key)
    if row is None:
        return RenderResult(ok=False, log=f"Application not found: {idempotency_key}")
    return render_tailored_pdf(
        row["country"],
        row["company_name"],
        row["job_url"],
        user_id=uid,
    )


def list_master_resumes(*, user_id: int | None = None) -> list[MasterResumeSummary]:
    uid = user_id if user_id is not None else resolve_user_id()
    items = repo.list_master_resumes(uid)
    return [
        item.model_copy(update={"pdf_filename": _master_pdf_filename(uid, item.slug)})
        for item in items
    ]


def get_application_profile(*, user_id: int | None = None) -> ApplicationProfile:
    uid = user_id if user_id is not None else resolve_user_id()
    docs = repo.get_user_documents(uid)
    if docs is None:
        return ApplicationProfile()
    raw = json.loads(docs.get("profile_json") or "{}")
    return ApplicationProfile(**raw)


def get_master_resume_detail(slug: str, *, user_id: int | None = None) -> dict:
    uid = user_id if user_id is not None else resolve_user_id()
    key = repo.normalize_master_resume_slug(slug)
    row = repo.get_master_resume_row(uid, slug)
    if row is None or not (row.get("content") or "").strip():
        raise LookupError(f"Master resume not found: {key}")
    return {
        "slug": key,
        "label": (row.get("label") or "").strip(),
        "content": row["content"],
        "updated_at": (row.get("updated_at") or "").strip(),
        "has_pdf": bool(row.get("pdf_bytes")),
        "pdf_updated_at": (row.get("pdf_updated_at") or "").strip(),
        "pdf_filename": _master_pdf_filename(uid, key),
    }


def read_master_pdf_download(
    slug: str,
    *,
    user_id: int | None = None,
) -> tuple[bytes, str]:
    uid = user_id if user_id is not None else resolve_user_id()
    key = repo.normalize_master_resume_slug(slug)
    pdf_bytes = repo.read_master_pdf_bytes(uid, key)
    return pdf_bytes, _master_pdf_filename(uid, key)


def render_master_pdf(
    slug: str,
    *,
    user_id: int | None = None,
) -> RenderResult:
    uid = user_id if user_id is not None else resolve_user_id()
    key = repo.normalize_master_resume_slug(slug)
    try:
        tex = repo.read_master_resume(uid, key)
    except LookupError as exc:
        return RenderResult(ok=False, log=str(exc))

    pdf_filename = _master_pdf_filename(uid, key)
    basename = pdf_filename.removesuffix(".pdf")

    with tempfile.TemporaryDirectory() as tmp:
        tex_path = Path(tmp) / f"{basename}.tex"
        tex_path.write_text(tex, encoding="utf-8")
        compiled = render.render_tex_to_pdf(tex_path)
        if not compiled.ok:
            return RenderResult(ok=False, log=compiled.log)

        pdf_bytes = Path(compiled.pdf_path).read_bytes()
        stored = repo.save_master_pdf(uid, key, pdf_bytes)
        return RenderResult(
            ok=True,
            log=compiled.log,
            pdf_stored=True,
            pdf_bytes=stored["pdf_bytes"],
            pdf_filename=pdf_filename,
        )


def save_master_resume(
    slug: str,
    content: str,
    *,
    label: str = "",
    user_id: int | None = None,
) -> dict:
    uid = user_id if user_id is not None else resolve_user_id()
    return repo.save_master_resume(uid, slug, content, label=label)


def save_application_profile(profile: ApplicationProfile, *, user_id: int | None = None) -> dict:
    uid = user_id if user_id is not None else resolve_user_id()
    return repo.save_profile(uid, profile)


def save_tailored_tex_for_job(
    country: str,
    company: str,
    url: str,
    content: str,
    *,
    master_resume_slug: str,
    user_id: int | None = None,
) -> dict:
    uid = user_id if user_id is not None else resolve_user_id()
    ctx = get_job_context(country, company, url, user_id=uid)
    slug = repo.normalize_master_resume_slug(master_resume_slug)
    overwritten = ctx.has_tailored_tex
    saved = repo.save_tailored_tex(
        uid,
        ctx.idempotency_key,
        content,
        country=ctx.country,
        company=ctx.company,
        url=ctx.url,
        master_resume_slug=slug,
    )
    meta = repo.touch_application_meta(
        uid,
        ctx.idempotency_key,
        country=ctx.country,
        company=ctx.company,
        url=ctx.url,
        event="tailored_tex_saved",
        extra={"master_resume_slug": slug, "overwritten": overwritten},
    )
    return {
        "idempotency_key": ctx.idempotency_key,
        "master_resume_slug": slug,
        "updated_at": saved["updated_at"],
        "overwritten": overwritten,
        "meta": meta,
    }


def validate_tailored_tex(
    country: str,
    company: str,
    url: str,
    *,
    tex_content: str | None = None,
    master_resume_slug: str | None = None,
    user_id: int | None = None,
) -> ValidationResult:
    uid = user_id if user_id is not None else resolve_user_id()
    ctx = get_job_context(country, company, url, user_id=uid)
    slug = _resolve_master_slug(uid, ctx.idempotency_key, master_resume_slug)
    master = repo.read_master_resume(uid, slug)
    tailored = (
        tex_content
        if tex_content is not None
        else repo.read_tailored_tex(uid, ctx.idempotency_key)
    )
    result = validate.validate_tex_content(tailored, master)
    repo.touch_application_meta(
        uid,
        ctx.idempotency_key,
        country=country,
        company=company,
        url=ctx.url,
        event="validated",
        extra={
            "validation_ok": result.ok,
            "issue_count": len(result.issues),
            "master_resume_slug": slug,
        },
    )
    return result


def render_tailored_pdf(
    country: str,
    company: str,
    url: str,
    *,
    master_resume_slug: str | None = None,
    user_id: int | None = None,
) -> RenderResult:
    uid = user_id if user_id is not None else resolve_user_id()
    ctx = get_job_context(country, company, url, user_id=uid)

    try:
        tex = repo.read_tailored_tex(uid, ctx.idempotency_key)
    except LookupError as exc:
        return RenderResult(ok=False, log=str(exc))

    validation = validate_tailored_tex(
        country,
        company,
        url,
        user_id=uid,
        master_resume_slug=master_resume_slug,
    )
    if not validation.ok:
        lines = [f"{issue.code}: {issue.message}" for issue in validation.issues]
        return RenderResult(ok=False, log="Validation failed:\n" + "\n".join(lines))

    pdf_filename = _application_pdf_filename(uid, company)
    basename = pdf_filename.removesuffix(".pdf")

    with tempfile.TemporaryDirectory() as tmp:
        tex_path = Path(tmp) / f"{basename}.tex"
        tex_path.write_text(tex, encoding="utf-8")
        compiled = render.render_tex_to_pdf(tex_path)
        if not compiled.ok:
            return RenderResult(ok=False, log=compiled.log)

        pdf_bytes = Path(compiled.pdf_path).read_bytes()
        stored = repo.save_pdf(uid, ctx.idempotency_key, pdf_bytes)
        slug = _resolve_master_slug(uid, ctx.idempotency_key, master_resume_slug)
        repo.touch_application_meta(
            uid,
            ctx.idempotency_key,
            country=country,
            company=company,
            url=ctx.url,
            event="pdf_rendered",
            extra={"pdf_bytes": stored["pdf_bytes"], "master_resume_slug": slug},
        )
        return RenderResult(
            ok=True,
            log=compiled.log,
            pdf_stored=True,
            pdf_bytes=stored["pdf_bytes"],
            pdf_filename=pdf_filename,
        )


def _parse_add_company_locations(raw: str | list[dict] | None) -> list[dict] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("locations must be a JSON array")
        return parsed
    if not raw:
        return None
    return raw


def _validate_add_company_inputs(
    name: str,
    careers_url: str,
    *,
    country: str,
    countries: list[str] | None,
    ats: str,
    locations: list[dict] | None,
) -> tuple[list[str] | None, str | None]:
    cleaned_name = (name or "").strip()
    cleaned_url = (careers_url or "").strip()
    if not cleaned_name:
        raise ValueError("Company name is required")
    if not cleaned_url:
        raise ValueError("Careers page URL is required")

    country_keys: list[str] | None = None
    if countries:
        country_keys = [
            (item or "").strip().lower()
            for item in countries
            if (item or "").strip()
        ]
        for key in country_keys:
            ensure_country_key(key)
    else:
        country_hint = (country or "").strip().lower()
        if country_hint and country_hint not in ("", "auto", "all"):
            country_keys = [ensure_country_key(country_hint)]

    if locations is not None and not isinstance(locations, list):
        raise ValueError("locations must be an array")

    ats_hint = (ats or "auto").strip().lower()
    valid_ats = {item["id"] for item in catalog_list_ats_types()}
    if ats_hint and ats_hint not in ("auto", "") and ats_hint not in valid_ats:
        raise ValueError(f"Unknown ATS: {ats_hint}")
    ats_hint_arg = None if ats_hint in ("", "auto") else ats_hint
    return country_keys, ats_hint_arg


def list_supported_countries() -> list[SupportedCountry]:
    return [
        SupportedCountry(id=key, label=label)
        for key, label in sorted(all_country_labels().items())
    ]


def add_country(label: str) -> SupportedCountry:
    result = add_custom_country(label)
    return SupportedCountry(id=result["id"], label=result["label"])


def list_ats_types() -> list[AtsTypeOption]:
    return [AtsTypeOption(**item) for item in catalog_list_ats_types()]


def add_company(
    name: str,
    careers_url: str,
    *,
    country: str = "auto",
    countries: list[str] | None = None,
    ats: str = "auto",
    locations: str | list[dict] | None = None,
) -> AddCompanyResult:
    parsed_locations = _parse_add_company_locations(locations)
    country_keys, ats_hint = _validate_add_company_inputs(
        name,
        careers_url,
        country=country,
        countries=countries,
        ats=ats,
        locations=parsed_locations,
    )
    result = catalog_add_company(
        name,
        careers_url,
        country_keys[0] if country_keys else None,
        country_keys=country_keys,
        ats_hint=ats_hint,
        locations=parsed_locations,
    )
    company_name = (result.get("name") or name).strip()
    slug = repo.company_slug(company_name)
    country_key = (result.get("country") or "").strip().lower()
    return AddCompanyResult(
        country=country_key,
        country_label=(result.get("country_label") or COUNTRY_LABELS.get(country_key, country_key)),
        name=company_name,
        company_slug=slug,
        careers_url=(result.get("careers_url") or careers_url).strip(),
        ats_type=(result.get("ats_type") or "").strip(),
        ats_url=(result.get("ats_url") or "").strip(),
        city=(result.get("city") or "").strip(),
        size=(result.get("size") or "").strip(),
        matching_jobs_count=len(result.get("matching_jobs") or []),
        workspace_path=f"/company/{country_key}/{slug}",
    )


def add_position(
    country: str,
    company: str,
    title: str,
    url: str,
    *,
    location: str = "",
    description_text: str = "",
    posted_at: str = "",
    overwrite: bool = False,
) -> AddPositionResult:
    country_key = (country or "").strip().lower()
    if not country_key or country_key == "all":
        raise ValueError("country is required (not 'all')")
    if country_key not in supported_countries():
        raise ValueError(f"Unknown country: {country_key}")

    cleaned_title = (title or "").strip()
    cleaned_url = (url or "").strip()
    if not cleaned_title:
        raise ValueError("title is required")
    if not cleaned_url:
        raise ValueError("url is required")

    cleaned_description = _validate_manual_jd(description_text, url=cleaned_url)
    cleaned_posted_at = _validate_posted_at(posted_at, url=cleaned_url)

    company_name = resolve_company_for_workspace(country_key, company)
    job: dict = {"title": cleaned_title, "url": cleaned_url}
    cleaned_location = (location or "").strip()
    if cleaned_location:
        job["location"] = cleaned_location
    if cleaned_description:
        job["description_text"] = cleaned_description
    _apply_posted_at_to_job(job, cleaned_posted_at)

    before_job = get_job_by_url(
        cleaned_url,
        company_name=company_name,
        country_key=country_key,
    )
    already_existed = before_job is not None
    before_description = (before_job or {}).get("description_text") or ""

    result = catalog_add_manual_jobs(country_key, company_name, [job])
    added = 0 if already_existed else int(result.get("added") or 0)

    stored = get_job_by_url(
        cleaned_url,
        company_name=company_name,
        country_key=country_key,
    )
    if stored is None:
        raise LookupError(f"Position not found after add: {cleaned_url}")

    idem_key = (stored.get("idempotency_key") or "").strip()
    description_saved = False
    if already_existed and overwrite:
        stored = update_matching_job_fields(
            country_key,
            company_name,
            lookup_url=cleaned_url,
            title=cleaned_title,
            location=cleaned_location if location else None,
            description_text=cleaned_description if description_text else None,
            posted_at=cleaned_posted_at if cleaned_posted_at else None,
        ) or stored
        description_saved = bool(description_text)
    elif already_existed and cleaned_posted_at and cleaned_posted_at != job_fetched_ts(before_job or {}):
        stored = update_matching_job_fields(
            country_key,
            company_name,
            lookup_url=cleaned_url,
            posted_at=cleaned_posted_at,
        ) or stored
    if cleaned_description and not (already_existed and overwrite):
        description_saved = _persist_job_description(
            idem_key,
            cleaned_description,
            existing=before_description,
            overwrite=overwrite,
        )
        if description_saved:
            stored = get_job_by_url(
                cleaned_url,
                company_name=company_name,
                country_key=country_key,
            ) or stored

    desc_fields = _job_description_fields(stored or {})
    has_description = bool(desc_fields.get("has_description"))
    description_chars = len((stored or {}).get("description_text") or "")
    canonical_url = (stored.get("url") or cleaned_url).strip()
    slug = repo.company_slug(company_name)
    return AddPositionResult(
        added=added,
        already_existed=already_existed,
        country=country_key,
        country_label=(result.get("country_label") or COUNTRY_LABELS.get(country_key, country_key)),
        company=company_name,
        company_slug=slug,
        title=(stored.get("title") or cleaned_title).strip(),
        url=canonical_url,
        idempotency_key=idem_key,
        location=(stored.get("location") or cleaned_location).strip(),
        has_description=has_description,
        needs_description=not has_description,
        needs_fetch=not has_description and not _non_fetchable_posting_url(canonical_url),
        description_chars=description_chars,
        description_saved=description_saved,
        total_positions=int(result.get("total") or 0),
        posted_at=job_fetched_ts(stored or {}),
        workspace_path=f"/company/{country_key}/{slug}",
    )


def save_position_description(
    country: str,
    company: str,
    url: str,
    description_text: str,
    *,
    overwrite: bool = False,
) -> SavePositionDescriptionResult:
    country_key = (country or "").strip().lower()
    cleaned_url = (url or "").strip()
    cleaned_description = (description_text or "").strip()
    if not cleaned_description and not overwrite:
        raise ValueError("description_text is required")
    if cleaned_description and len(cleaned_description) < _MIN_JD_CHARS and not overwrite:
        raise ValueError(f"description_text is too short (need at least {_MIN_JD_CHARS} characters)")

    company_name, job = _resolve_catalog_position(country_key, company, cleaned_url)

    idem_key = (job.get("idempotency_key") or "").strip()
    before = (job.get("description_text") or "").strip()
    saved = _persist_job_description(
        idem_key,
        cleaned_description,
        existing=before,
        overwrite=overwrite,
    )
    stored = get_job_by_url(
        cleaned_url,
        company_name=company_name,
        country_key=country_key,
    ) or job
    desc_fields = _job_description_fields(stored)
    has_description = bool(desc_fields.get("has_description"))
    after = (stored.get("description_text") or "").strip()
    return SavePositionDescriptionResult(
        country=country_key,
        company=company_name,
        url=(stored.get("url") or cleaned_url).strip(),
        idempotency_key=idem_key,
        has_description=has_description,
        needs_fetch=not has_description,
        description_chars=len(after),
        description_saved=saved,
        appended=saved and not overwrite and bool(before) and after != before and before in after,
        overwritten=saved and overwrite,
    )


def update_position(
    country: str,
    company: str,
    url: str,
    *,
    title: str | None = None,
    new_url: str | None = None,
    location: str | None = None,
    description_text: str | None = None,
    clear_description: bool = False,
    posted_at: str | None = None,
) -> UpdatePositionResult:
    country_key = (country or "").strip().lower()
    if not country_key or country_key == "all":
        raise ValueError("country is required (not 'all')")

    company_name, job = _resolve_catalog_position(country_key, company, url)
    lookup_url = (url or "").strip()

    updated_fields: list[str] = []
    patch_title = (title or "").strip() if title is not None else None
    patch_url = (new_url or "").strip() if new_url is not None else None
    patch_location = location if location is not None else None
    patch_description: str | None = None
    patch_posted_at: str | None = None
    if clear_description:
        patch_description = ""
        updated_fields.append("description_text")
    elif description_text is not None:
        patch_description = (description_text or "").strip()
        updated_fields.append("description_text")
    if posted_at is not None:
        patch_posted_at = normalize_posted_at(posted_at)
        updated_fields.append("posted_at")

    if patch_title is not None:
        if not patch_title:
            raise ValueError("title cannot be empty")
        updated_fields.append("title")
    if patch_url is not None:
        if not patch_url:
            raise ValueError("new_url cannot be empty")
        updated_fields.append("url")
    if patch_location is not None:
        updated_fields.append("location")

    if not updated_fields:
        raise ValueError(
            "at least one field to update is required "
            "(title, new_url, location, description_text, posted_at, or clear_description)"
        )

    stored = update_matching_job_fields(
        country_key,
        company_name,
        lookup_url=lookup_url,
        title=patch_title,
        url=patch_url,
        location=patch_location,
        description_text=patch_description,
        posted_at=patch_posted_at,
    )
    if stored is None:
        raise LookupError(f"Position not found: {lookup_url}")

    return _position_result_from_job(
        country_key=country_key,
        company_name=company_name,
        job=stored,
        updated_fields=updated_fields,
    )


def mark_job_applied(
    country: str,
    company: str,
    url: str,
    *,
    applied: bool = True,
    user_id: int | None = None,
) -> dict:
    uid = user_id if user_id is not None else resolve_user_id()
    result = set_job_applied(country, company, url, applied, user_id=uid)
    ctx = get_job_context(country, company, url, user_id=uid)
    repo.touch_application_meta(
        uid,
        ctx.idempotency_key,
        country=country,
        company=company,
        url=ctx.url,
        event="marked_applied" if applied else "marked_unapplied",
    )
    return result
