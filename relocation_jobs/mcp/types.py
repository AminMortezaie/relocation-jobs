from __future__ import annotations

from pydantic import Field, field_validator

from relocation_jobs.shared.schema import BaseSchema


class ValidationIssue(BaseSchema):
    code: str
    message: str


class ValidationResult(BaseSchema):
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class RenderResult(BaseSchema):
    ok: bool
    log: str = ""
    pdf_stored: bool = False
    pdf_bytes: int = 0


class MasterResumeSummary(BaseSchema):
    slug: str
    label: str = ""
    updated_at: str = ""


class ApplicationProfile(BaseSchema):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    location: str = ""
    work_authorization: str = ""
    notice_period: str = ""
    summary: str = ""
    pipeline: list[str] = Field(default_factory=list)

    @field_validator("pipeline")
    @classmethod
    def _pipeline_max_five(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) > 5:
            raise ValueError("pipeline may contain at most 5 prompts")
        return cleaned


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
    master_resume_slug: str = ""
    has_tailored_tex: bool = False
    has_pdf: bool = False


class ApplicationQueueItem(BaseSchema):
    country: str
    company: str
    url: str
    title: str = ""
    idempotency_key: str = ""
    pinned: bool = False
    looking_to_apply: bool = False
    ats_score: int | None = None
