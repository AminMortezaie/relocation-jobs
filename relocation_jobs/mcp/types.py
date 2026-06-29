from __future__ import annotations

from pydantic import Field

from relocation_jobs.shared.schema import BaseSchema


class ValidationIssue(BaseSchema):
    code: str
    message: str


class ValidationResult(BaseSchema):
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class RenderResult(BaseSchema):
    ok: bool
    pdf_path: str = ""
    log: str = ""


class ApplicationProfile(BaseSchema):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    location: str = ""
    work_authorization: str = ""
    notice_period: str = ""
    summary: str = ""


class JobContext(BaseSchema):
    country: str
    company: str
    url: str
    title: str = ""
    idempotency_key: str = ""
    ats_type: str = ""
    ats_url: str = ""
    location: str = ""
    visa_sponsorship: bool | None = None
    applied: bool = False
    rejected: bool = False
    looking_to_apply: bool = False
    pinned: bool = False
    ats_score: int | None = None
    application_dir: str = ""
    tailored_tex_path: str = ""
    pdf_path: str = ""


class ApplicationQueueItem(BaseSchema):
    country: str
    company: str
    url: str
    title: str = ""
    idempotency_key: str = ""
    pinned: bool = False
    looking_to_apply: bool = False
    ats_score: int | None = None
