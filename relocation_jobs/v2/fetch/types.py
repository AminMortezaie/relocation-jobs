from __future__ import annotations

from enum import Enum
from typing import Optional

from relocation_jobs.v2.shared.schema import BaseSchema


class AttemptStatus(str, Enum):
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


class CompanyFetchAttempt(BaseSchema):
    id: int
    country: str
    company_name: str
    started_at: str
    status: AttemptStatus
    fetch_run_id: Optional[int] = None
    careers_url: Optional[str] = None
    ats_type: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
    jobs_total: Optional[int] = None
    jobs_new: Optional[int] = None
    jobs_preserved: Optional[int] = None
    message: Optional[str] = None
    duration_seconds: Optional[float] = None

    @classmethod
    def from_row(cls, row: dict) -> CompanyFetchAttempt:
        return cls.model_validate(dict(row))
