from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from relocation_jobs.users.repo import get_user_by_id
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
    """Load job and tracking context for an application (title, ATS, JD text, flags, artifact state).

    Use description_text as the job description for reframe phases — do not scrape the posting
    URL in chat. When has_description is false (needs_fetch is true), the user should fetch the
    JD on the panel (company workspace → Fetch job description) or via catalog enrich, then call
    this tool again.

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
def list_looking_to_apply_jobs(country: str = "") -> str:
    """List only jobs in looking-to-apply state for the configured MCP user."""
    scope = country.strip() or None
    items = service.list_looking_to_apply_jobs(country=scope)
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
def list_project_masters() -> str:
    """List project masters for the MCP user (slug, label, updated_at).

    Project masters are LaTeX fragments used as a reframe evidence bank —
    not employment history and not pasted wholesale into tailored CVs without approval.
    """
    items = service.list_project_masters()
    return _json([item.model_dump() for item in items])


@mcp.tool()
def get_project_master(slug: str) -> str:
    """Read one project master LaTeX body by slug (e.g. relocation-jobs)."""
    uid = service.resolve_user_id()
    return mcp_repo.read_project_master(uid, slug)


@mcp.tool()
def save_project_master(slug: str, content: str, label: str = "") -> str:
    """Create or update a project master LaTeX fragment for the MCP user."""
    return _json(service.save_project_master(slug, content, label=label))


@mcp.tool()
def get_mcp_status() -> str:
    """Return MCP user identity and whether profile / master resumes / project masters exist (debug user mismatch)."""
    uid = service.resolve_user_id()
    user = get_user_by_id(uid) or {}
    profile = service.get_application_profile(user_id=uid)
    masters = service.list_master_resumes(user_id=uid)
    projects = service.list_project_masters(user_id=uid)
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
        "project_master_count": len(projects),
        "project_master_slugs": [item.slug for item in projects],
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
def save_cover_letter_tex(
    country: str,
    company: str,
    url: str,
    content: str,
) -> str:
    """Save cover letter LaTeX for this job.

    Overwrites any existing cover letter tex. Job must exist in the catalog
    (call get_job_context first and use the url/country/company it returns).
    Prefer rendering PDF on the panel rather than render_cover_letter_pdf in chat.
    """
    return _json(service.save_cover_letter_tex_for_job(country, company, url, content))


@mcp.tool()
def render_cover_letter_pdf(country: str, company: str, url: str) -> str:
    """Compile saved cover letter tex to PDF and store the PDF bytes in Postgres."""
    return _json(service.render_cover_letter_pdf(country, company, url))


@mcp.tool()
def set_ats_score(country: str, company: str, url: str, ats_score: int | None = None) -> str:
    """Set or clear the ATS score for a job (0-100). Use None to clear."""
    return _json(service.set_ats_score(country, company, url, ats_score))


@mcp.tool()
def mark_applied(country: str, company: str, url: str, applied: bool = True) -> str:
    """Mark the job applied (or unapplied) in the panel tracking DB."""
    return _json(service.mark_job_applied(country, company, url, applied=applied))


@mcp.tool()
def list_supported_countries() -> str:
    """List catalog country keys for add_company (built-ins plus any custom countries)."""
    items = service.list_supported_countries()
    return _json([item.model_dump() for item in items])


@mcp.tool()
def add_country(label: str) -> str:
    """Register a custom catalog country (e.g. Armenia) before add_company, or let add_company auto-register from country key."""
    return _json(service.add_country(label).model_dump())


@mcp.tool()
def list_ats_types() -> str:
    """List ATS type ids for add_company (use auto to detect from the careers URL)."""
    items = service.list_ats_types()
    return _json([item.model_dump() for item in items])


@mcp.tool()
def add_position(
    country: str,
    company: str,
    title: str,
    url: str,
    location: str = "",
    description_text: str = "",
    posted_at: str = "",
    overwrite: bool = False,
) -> str:
    """Add a position to an existing company and store its job description in the catalog.

    Use when a role is visible outside the company careers site (e.g. LinkedIn only).
    Company must already exist (add_company first).

    Required: country, company (name or slug), title, posting url.
    description_text: paste the full JD from the posting. Required for LinkedIn / Indeed /
    Glassdoor URLs (panel fetch will not work). For ATS URLs it is optional — omit only if
    you will fetch the JD on the panel or call save_position_description later.
    posted_at: when the role was posted (YYYY-MM-DD or ISO datetime). Required for LinkedIn /
    Indeed / Glassdoor — use the date shown on the listing, not today's date. Drives board
    sort (stored as fetched/last_seen).
    Optional: location, overwrite (when true and the URL already exists, replace title,
    location, description, and/or posted_at instead of merging).

    Returns canonical url, idempotency_key, posted_at, has_description, needs_description,
    needs_fetch, and workspace_path. Call get_job_context next for reframe phases.
    """
    return _json(service.add_position(
        country,
        company,
        title,
        url,
        location=location,
        description_text=description_text,
        posted_at=posted_at,
        overwrite=overwrite,
    ))


@mcp.tool()
def save_position_description(
    country: str,
    company: str,
    url: str,
    description_text: str,
    overwrite: bool = False,
) -> str:
    """Store or update a job description for an existing catalog position.

    Default: merge with existing text (append or replace when the new paste is fuller).
    Set overwrite=true to replace the stored JD entirely (use to fix mistakes). Pass an
    empty description_text with overwrite=true to clear the JD.
    """
    return _json(service.save_position_description(
        country,
        company,
        url,
        description_text,
        overwrite=overwrite,
    ))


@mcp.tool()
def update_position(
    country: str,
    company: str,
    url: str,
    title: str = "",
    new_url: str = "",
    location: str = "",
    description_text: str = "",
    clear_description: bool = False,
    posted_at: str = "",
) -> str:
    """Overwrite catalog fields for an existing position (fix mistaken saves).

    Identify the role by country, company, and current url. Pass only fields to change;
    omitted fields stay as-is. description_text replaces the full JD (not merged).
    posted_at sets the real posting date (YYYY-MM-DD or ISO datetime) for board sort.
    Set clear_description=true to wipe the JD. new_url updates the posting link and
    idempotency key (use get_job_context afterward for the canonical url).
    """
    optional_title = title.strip() or None
    optional_url = new_url.strip() or None
    optional_location = location if location else None
    optional_description = description_text.strip() if description_text.strip() else None
    optional_posted_at = posted_at.strip() if posted_at.strip() else None

    return _json(service.update_position(
        country,
        company,
        url,
        title=optional_title,
        new_url=optional_url,
        location=optional_location,
        description_text=optional_description,
        clear_description=clear_description,
        posted_at=optional_posted_at,
    ))


@mcp.tool()
def add_company(
    name: str,
    careers_url: str,
    country: str = "auto",
    countries: list[str] | None = None,
    ats: str = "auto",
    locations_json: str = "",
) -> str:
    """Add a company to the catalog — same flow as the panel Add company dialog.

    Required: name and careers_url (public careers or ATS board URL).
    Optional: country or countries (omit or use auto to detect from URL / relocate.me);
    ats (auto, greenhouse, lever, ashby, … — call list_ats_types); locations_json as a JSON
    array of objects with country and city keys when country is set manually.
    Runs ATS detection and metadata enrichment like the panel. Returns workspace_path
    for the company workspace on the panel.
    """
    locations = locations_json.strip() or None
    return _json(service.add_company(
        name,
        careers_url,
        country=country,
        countries=countries,
        ats=ats,
        locations=locations,
    ))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
