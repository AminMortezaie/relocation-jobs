from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from relocation_jobs.catalog.repo import get_company, get_job_by_url
from relocation_jobs.core.db import _normalize_url
from relocation_jobs.core.job_identity import job_idempotency_key
from relocation_jobs.db.users import get_user_by_username
from relocation_jobs.mcp import repo, render, validate
from relocation_jobs.mcp.types import (
    ApplicationProfile,
    ApplicationQueueItem,
    ApplicationTexDetail,
    CompanyApplicationsResponse,
    CompanyPositionApplication,
    JobContext,
    MasterResumeSummary,
    RenderResult,
    ValidationResult,
)
from relocation_jobs.positions.service import set_job_applied
from relocation_jobs.users.repo import load_job_tracking


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


def get_job_context(
    country: str,
    company: str,
    url: str,
    *,
    user_id: int | None = None,
) -> JobContext:
    uid = user_id if user_id is not None else resolve_user_id()
    job = get_job_by_url(url, company_name=company, country_key=country)
    if job is None:
        raise LookupError(f"Job not found: {company} — {url[:120]}")

    company_row = get_company(country, company) or {}
    catalog_url = (job.get("url") or url).strip()
    idem_key = (job.get("idempotency_key") or "").strip() or job_idempotency_key(catalog_url)
    tracking = load_job_tracking(uid, country=country)
    row = _tracking_row(tracking, country, company, catalog_url)
    app_state = _application_state(uid, idem_key)

    return JobContext(
        country=country,
        company=company,
        url=catalog_url,
        title=(job.get("title") or "").strip(),
        idempotency_key=idem_key,
        ats_type=(company_row.get("ats_type") or "").strip(),
        ats_url=(company_row.get("ats_url") or "").strip(),
        location=(job.get("location") or "").strip(),
        visa_sponsorship=job.get("visa_sponsorship"),
        applied=bool(row.get("applied")),
        rejected=bool(row.get("rejected")),
        looking_to_apply=bool(row.get("looking_to_apply")),
        pinned=bool(row.get("pinned")),
        ats_score=row.get("ats_score"),
        master_resume_slug=app_state["master_slug"],
        has_tailored_tex=app_state["has_tex"],
        has_pdf=app_state["has_pdf"],
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
    app_by_key = {
        (row.get("idempotency_key") or "").strip(): row
        for row in app_rows
        if (row.get("idempotency_key") or "").strip()
    }

    positions: list[CompanyPositionApplication] = []
    for job in company_row.get("matching_jobs") or []:
        catalog_url = (job.get("url") or "").strip()
        idem_key = (
            (job.get("idempotency_key") or "").strip()
            or job_idempotency_key(catalog_url)
        )
        row = _tracking_row(tracking, country_key, company_name, catalog_url)
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
        ))

    positions.sort(key=lambda item: (not item.pinned, not item.looking_to_apply, item.title.lower()))
    return CompanyApplicationsResponse(
        country=country_key,
        company=company_name,
        company_slug=repo.company_slug(company_name),
        positions=positions,
    )


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


def read_application_pdf(
    idempotency_key: str,
    *,
    user_id: int | None = None,
) -> bytes:
    uid = user_id if user_id is not None else resolve_user_id()
    return repo.read_pdf_bytes(uid, idempotency_key)


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
    return repo.list_master_resumes(uid)


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
    content = repo.read_master_resume(uid, slug)
    summaries = {item.slug: item for item in repo.list_master_resumes(uid)}
    summary = summaries.get(key)
    return {
        "slug": key,
        "label": (summary.label if summary else ""),
        "content": content,
        "updated_at": (summary.updated_at if summary else ""),
    }


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
    saved = repo.save_tailored_tex(
        uid,
        ctx.idempotency_key,
        content,
        country=country,
        company=company,
        url=ctx.url,
        master_resume_slug=slug,
    )
    meta = repo.touch_application_meta(
        uid,
        ctx.idempotency_key,
        country=country,
        company=company,
        url=ctx.url,
        event="tailored_tex_saved",
        extra={"master_resume_slug": slug},
    )
    return {
        "idempotency_key": ctx.idempotency_key,
        "master_resume_slug": slug,
        "updated_at": saved["updated_at"],
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

    with tempfile.TemporaryDirectory() as tmp:
        tex_path = Path(tmp) / "resume.tex"
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
