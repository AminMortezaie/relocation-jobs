from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from relocation_jobs.mcp import paths, repo as mcp_repo
from relocation_jobs.mcp import service

mcp = FastMCP("relocation-jobs")


def _json(payload) -> str:
    if hasattr(payload, "model_dump"):
        return json.dumps(payload.model_dump(), indent=2)
    return json.dumps(payload, indent=2)


@mcp.tool()
def get_job_context(country: str, company: str, url: str) -> str:
    """Load job and tracking context for an application (title, ATS, flags, artifact paths)."""
    return _json(service.get_job_context(country, company, url))


@mcp.tool()
def list_application_queue(country: str = "") -> str:
    """List pinned and looking-to-apply jobs for the configured MCP user."""
    scope = country.strip() or None
    items = service.list_application_queue(country=scope)
    return _json([item.model_dump() for item in items])


@mcp.tool()
def get_master_resume() -> str:
    """Read the canonical master resume tex from data/mcp/master_resume.tex."""
    return mcp_repo.read_master_resume()


@mcp.tool()
def get_application_profile() -> str:
    """Read static application profile (name, email, LinkedIn, work authorization, …)."""
    return _json(mcp_repo.read_profile())


@mcp.tool()
def save_tailored_tex(country: str, company: str, url: str, content: str) -> str:
    """Save a tailored resume tex for this job under data/mcp/applications/<key>/."""
    return _json(service.save_tailored_tex_for_job(country, company, url, content))


@mcp.tool()
def validate_tex(country: str, company: str, url: str, tex_content: str = "") -> str:
    """Validate tailored tex against master resume (structure + fact checks)."""
    optional = tex_content.strip() or None
    return _json(service.validate_tailored_tex(country, company, url, tex_content=optional))


@mcp.tool()
def render_pdf(country: str, company: str, url: str) -> str:
    """Compile saved tailored tex to PDF using MCP_LATEX_CMD (default: tectonic)."""
    return _json(service.render_tailored_pdf(country, company, url))


@mcp.tool()
def mark_applied(country: str, company: str, url: str, applied: bool = True) -> str:
    """Mark the job applied (or unapplied) in the panel tracking DB."""
    return _json(service.mark_job_applied(country, company, url, applied=applied))


def main() -> None:
    paths.ensure_data_layout()
    mcp.run()


if __name__ == "__main__":
    main()
