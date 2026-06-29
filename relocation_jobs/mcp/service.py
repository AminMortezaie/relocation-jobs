from __future__ import annotations

import os

from relocation_jobs.catalog.repo import get_company, get_job_by_url
from relocation_jobs.core.db import _normalize_url
from relocation_jobs.core.job_identity import job_idempotency_key
from relocation_jobs.db.users import get_user_by_username
from relocation_jobs.mcp import paths, repo, render, validate
from relocation_jobs.mcp.types import (
    ApplicationQueueItem,
    JobContext,
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

    app_dir = paths.application_dir(idem_key)
    tex = paths.tailored_tex_path(idem_key)
    pdf = paths.pdf_path(idem_key)

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
        application_dir=str(app_dir),
        tailored_tex_path=str(tex) if tex.is_file() else "",
        pdf_path=str(pdf) if pdf.is_file() else "",
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


def save_tailored_tex_for_job(
    country: str,
    company: str,
    url: str,
    content: str,
    *,
    user_id: int | None = None,
) -> dict:
    ctx = get_job_context(country, company, url, user_id=user_id)
    path = repo.save_tailored_tex(ctx.idempotency_key, content)
    meta = repo.touch_application_meta(
        ctx.idempotency_key,
        country=country,
        company=company,
        url=ctx.url,
        event="tailored_tex_saved",
    )
    return {
        "path": str(path),
        "idempotency_key": ctx.idempotency_key,
        "meta": meta,
    }


def validate_tailored_tex(
    country: str,
    company: str,
    url: str,
    *,
    tex_content: str | None = None,
    user_id: int | None = None,
) -> ValidationResult:
    ctx = get_job_context(country, company, url, user_id=user_id)
    master = repo.read_master_resume()
    tailored = tex_content if tex_content is not None else repo.read_tailored_tex(ctx.idempotency_key)
    result = validate.validate_tex_content(tailored, master)
    repo.touch_application_meta(
        ctx.idempotency_key,
        country=country,
        company=company,
        url=ctx.url,
        event="validated",
        extra={"validation_ok": result.ok, "issue_count": len(result.issues)},
    )
    return result


def render_tailored_pdf(
    country: str,
    company: str,
    url: str,
    *,
    user_id: int | None = None,
) -> RenderResult:
    ctx = get_job_context(country, company, url, user_id=user_id)
    tex_path = paths.tailored_tex_path(ctx.idempotency_key)
    if not tex_path.is_file():
        return RenderResult(ok=False, log=f"No tailored tex at {tex_path}")

    validation = validate_tailored_tex(country, company, url, user_id=user_id)
    if not validation.ok:
        lines = [f"{issue.code}: {issue.message}" for issue in validation.issues]
        return RenderResult(ok=False, log="Validation failed:\n" + "\n".join(lines))

    result = render.render_tex_to_pdf(tex_path)
    if result.ok:
        repo.touch_application_meta(
            ctx.idempotency_key,
            country=country,
            company=company,
            url=ctx.url,
            event="pdf_rendered",
            extra={"pdf_path": result.pdf_path},
        )
    return result


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
        ctx.idempotency_key,
        country=country,
        company=company,
        url=ctx.url,
        event="marked_applied" if applied else "marked_unapplied",
    )
    return result
