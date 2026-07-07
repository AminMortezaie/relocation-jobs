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
    pdf_filename: str = ""


class MasterResumeSummary(BaseSchema):
    slug: str
    label: str = ""
    updated_at: str = ""
    has_pdf: bool = False
    pdf_filename: str = ""


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
    in_application_queue: bool = False
    can_save_tailored_tex: bool = True
    ats_score: int | None = None
    master_resume_slug: str = ""
    has_tailored_tex: bool = False
    has_pdf: bool = False
    pdf_filename: str = ""
    description_text: str = ""
    description_html: str = ""
    has_description: bool = False
    needs_fetch: bool = False
    posted_at: str = ""


class PositionDescription(BaseSchema):
    idempotency_key: str
    country: str = ""
    company: str = ""
    url: str = ""
    title: str = ""
    description_text: str = ""
    description_html: str = ""
    has_description: bool = False
    needs_fetch: bool = False


class ApplicationQueueItem(BaseSchema):
    country: str
    company: str
    url: str
    title: str = ""
    idempotency_key: str = ""
    pinned: bool = False
    looking_to_apply: bool = False
    ats_score: int | None = None


class CompanyPositionApplication(BaseSchema):
    title: str = ""
    url: str = ""
    idempotency_key: str = ""
    location: str = ""
    applied: bool = False
    rejected: bool = False
    looking_to_apply: bool = False
    pinned: bool = False
    ats_score: int | None = None
    has_tailored_tex: bool = False
    has_pdf: bool = False
    master_resume_slug: str = ""
    tailored_tex_updated_at: str = ""
    pdf_updated_at: str = ""
    pdf_filename: str = ""
    has_description: bool = False


class CompanyApplicationsResponse(BaseSchema):
    country: str
    company: str
    company_slug: str = ""
    positions: list[CompanyPositionApplication] = Field(default_factory=list)


class ApplicationTexDetail(BaseSchema):
    idempotency_key: str
    country: str = ""
    company: str = ""
    url: str = ""
    title: str = ""
    content: str = ""
    master_resume_slug: str = ""
    updated_at: str = ""


class SupportedCountry(BaseSchema):
    id: str
    label: str


class AtsTypeOption(BaseSchema):
    id: str
    label: str


class AddCompanyResult(BaseSchema):
    ok: bool = True
    country: str
    country_label: str
    name: str
    company_slug: str
    careers_url: str
    ats_type: str = ""
    ats_url: str = ""
    city: str = ""
    size: str = ""
    matching_jobs_count: int = 0
    workspace_path: str = ""


class AddPositionResult(BaseSchema):
    ok: bool = True
    added: int = 0
    already_existed: bool = False
    country: str
    country_label: str
    company: str
    company_slug: str
    title: str
    url: str
    idempotency_key: str = ""
    location: str = ""
    has_description: bool = False
    needs_description: bool = False
    needs_fetch: bool = False
    description_chars: int = 0
    description_saved: bool = False
    total_positions: int = 0
    posted_at: str = ""
    workspace_path: str = ""


class SavePositionDescriptionResult(BaseSchema):
    ok: bool = True
    country: str
    company: str
    url: str
    idempotency_key: str = ""
    has_description: bool = False
    needs_fetch: bool = False
    description_chars: int = 0
    description_saved: bool = False
    appended: bool = False
    overwritten: bool = False


class UpdatePositionResult(BaseSchema):
    ok: bool = True
    country: str
    company: str
    company_slug: str
    title: str = ""
    url: str = ""
    idempotency_key: str = ""
    location: str = ""
    has_description: bool = False
    needs_description: bool = False
    description_chars: int = 0
    updated_fields: list[str] = Field(default_factory=list)
    posted_at: str = ""
    workspace_path: str = ""
