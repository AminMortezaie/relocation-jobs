from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from relocation_jobs.db.users import get_user_by_id
from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.mcp import service
from relocation_jobs.mcp.types import ApplicationProfile

mcp = FastMCP("relocation-jobs")


def _json(payload) -> str:
    if hasattr(payload, "model_dump"):
        return json.dumps(payload.model_dump(), indent=2)
    return json.dumps(payload, indent=2)


@mcp.tool()
def get_job_context(country: str, company: str, url: str) -> str:
    """Load job and tracking context for an application (title, ATS, flags, artifact state).

    can_save_tailored_tex is true whenever the job exists in the catalog — queue membership
    (pinned / looking_to_apply) is not required. Use the returned country, company, and url
    for save_tailored_tex (overwrites any previous tailored tex).
    """
    return _json(service.get_job_context(country, company, url))


@mcp.tool()
def list_application_queue(country: str = "") -> str:
    """List pinned and looking-to-apply jobs for the configured MCP user."""
    scope = country.strip() or None
    items = service.list_application_queue(country=scope)
    return _json([item.model_dump() for item in items])


@mcp.tool()
def list_master_resumes() -> str:
    """List master resume variants for the MCP user (slug, label, updated_at)."""
    items = service.list_master_resumes()
    return _json([item.model_dump() for item in items])


@mcp.tool()
def get_master_resume(slug: str) -> str:
    """Read one master resume tex by slug (e.g. go, java, fullstack)."""
    uid = service.resolve_user_id()
    return mcp_repo.read_master_resume(uid, slug)


@mcp.tool()
def save_master_resume(slug: str, content: str, label: str = "") -> str:
    """Create or update a master resume variant for the MCP user."""
    return _json(service.save_master_resume(slug, content, label=label))


@mcp.tool()
def get_mcp_status() -> str:
    """Return MCP user identity and whether profile / master resumes exist (debug user mismatch)."""
    uid = service.resolve_user_id()
    user = get_user_by_id(uid) or {}
    profile = service.get_application_profile(user_id=uid)
    masters = service.list_master_resumes(user_id=uid)
    has_profile = any(
        getattr(profile, field, "")
        for field in (
            "full_name",
            "email",
            "phone",
            "linkedin_url",
            "location",
            "work_authorization",
            "notice_period",
            "summary",
        )
    )
    return _json({
        "user_id": uid,
        "username": (user.get("username") or "").strip(),
        "has_profile": has_profile,
        "pipeline_prompt_count": len(profile.pipeline),
        "master_resume_count": len(masters),
        "master_resume_slugs": [item.slug for item in masters],
    })


@mcp.tool()
def get_application_profile() -> str:
    """Read application profile from Postgres: contact fields, summary, and pipeline (ordered reframe prompts)."""
    uid = service.resolve_user_id()
    profile = service.get_application_profile(user_id=uid)
    return _json(profile)


@mcp.tool()
def get_reframe_pipeline() -> str:
    """Return ordered pipeline prompts to run in chat before reframing a resume for a job.

    There is no run_pipeline tool — Claude runs each prompt sequentially using job context.
    Same data as get_application_profile().pipeline; use this when you only need the prompts.
    """
    uid = service.resolve_user_id()
    profile = service.get_application_profile(user_id=uid)
    return _json({
        "pipeline": profile.pipeline,
        "count": len(profile.pipeline),
        "run_in_order": True,
    })


@mcp.tool()
def save_application_profile(
    full_name: str = "",
    email: str = "",
    phone: str = "",
    linkedin_url: str = "",
    location: str = "",
    work_authorization: str = "",
    notice_period: str = "",
    summary: str = "",
    pipeline: list[str] | None = None,
) -> str:
    """Save application profile for the MCP user (contact fields, summary, pipeline prompts)."""
    fields = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "linkedin_url": linkedin_url,
        "location": location,
        "work_authorization": work_authorization,
        "notice_period": notice_period,
        "summary": summary,
    }
    if pipeline is not None:
        fields["pipeline"] = pipeline
    profile = ApplicationProfile(**fields)
    return _json(service.save_application_profile(profile))


@mcp.tool()
def save_tailored_tex(
    country: str,
    company: str,
    url: str,
    content: str,
    master_resume_slug: str,
) -> str:
    """Save tailored resume tex for this job, tied to a master resume slug.

    Overwrites any existing tailored tex. Does not require the job to be pinned or marked
    looking-to-apply — only that it exists in the catalog (call get_job_context first and
    use the url/country/company it returns).
    """
    return _json(service.save_tailored_tex_for_job(
        country, company, url, content, master_resume_slug=master_resume_slug,
    ))


@mcp.tool()
def validate_tex(
    country: str,
    company: str,
    url: str,
    master_resume_slug: str = "",
    tex_content: str = "",
) -> str:
    """Validate tailored tex against master resume (structure + fact checks)."""
    optional_tex = tex_content.strip() or None
    optional_slug = master_resume_slug.strip() or None
    return _json(service.validate_tailored_tex(
        country, company, url,
        tex_content=optional_tex,
        master_resume_slug=optional_slug,
    ))


@mcp.tool()
def render_pdf(country: str, company: str, url: str, master_resume_slug: str = "") -> str:
    """Compile saved tailored tex to PDF and store the PDF bytes in Postgres."""
    optional_slug = master_resume_slug.strip() or None
    return _json(service.render_tailored_pdf(
        country, company, url, master_resume_slug=optional_slug,
    ))


@mcp.tool()
def mark_applied(country: str, company: str, url: str, applied: bool = True) -> str:
    """Mark the job applied (or unapplied) in the panel tracking DB."""
    return _json(service.mark_job_applied(country, company, url, applied=applied))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
