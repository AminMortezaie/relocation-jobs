from __future__ import annotations

from enum import Enum

from pydantic import Field

from relocation_jobs.v2.shared.coerce import as_bool
from relocation_jobs.v2.shared.predicates import any_of
from relocation_jobs.v2.shared.schema import BaseSchema


class PositionAction(str, Enum):
    APPLY = "apply"
    UNAPPLY = "unapply"
    REJECT = "reject"
    CLEAR_REJECT = "clear_reject"
    MARK_NOT_FOR_ME = "not_for_me"
    CLEAR_NOT_FOR_ME = "clear_not_for_me"
    LOOKING_TO_APPLY = "looking_to_apply"
    CLEAR_LOOKING_TO_APPLY = "clear_looking_to_apply"
    MARK_SEEN = "seen"
    CLEAR_SEEN = "clear_seen"
    WAITING_REFERRAL = "waiting_referral"
    CLEAR_WAITING_REFERRAL = "clear_waiting_referral"
    SET_ATS_SCORE = "set_ats_score"


class PositionBucket(str, Enum):
    JOBS = "jobs"
    REJECTED = "rejected_jobs"
    NOT_FOR_ME = "not_for_me_jobs"


class TrackingFlags(BaseSchema):
    applied: bool = False
    rejected: bool = False
    not_for_me: bool = False
    looking_to_apply: bool = False
    waiting_referral: bool = False
    seen: bool = False
    not_for_me_reason: str = ""

    @classmethod
    def from_row(cls, row: dict | None) -> TrackingFlags:
        if not row:
            return cls()
        return cls(
            applied=bool(row.get("applied")),
            rejected=as_bool(row.get("rejected")),
            not_for_me=bool(row.get("not_for_me")),
            looking_to_apply=bool(row.get("looking_to_apply")),
            waiting_referral=bool(row.get("waiting_referral")),
            seen=as_bool(row.get("seen")),
            not_for_me_reason=(row.get("not_for_me_reason") or "").strip(),
        )

    @classmethod
    def from_job_panel_dict(cls, job: dict) -> TrackingFlags:
        return cls(
            applied=bool(job.get("applied")),
            rejected=as_bool(job.get("rejected")),
            not_for_me=bool(job.get("not_for_me")),
            looking_to_apply=bool(job.get("looking_to_apply")),
            waiting_referral=bool(job.get("waiting_referral")),
            seen=as_bool(job.get("seen")),
            not_for_me_reason=(job.get("not_for_me_reason") or "").strip(),
        )

    def has_active_tracking(self) -> bool:
        if self.not_for_me:
            return False
        return any_of(self, _ACTIVE_TRACKING_RULES)


_ACTIVE_TRACKING_RULES: tuple = (
    lambda flags: flags.applied,
    lambda flags: flags.rejected,
    lambda flags: flags.looking_to_apply,
)


class PositionFilters(BaseSchema):
    hide_applied: bool = False
    hide_rejected: bool = False
    applied_only: bool = False
    rejected_only: bool = False
    looking_to_apply_only: bool = False


class PositionView(BaseSchema):
    flags: TrackingFlags
    bucket: PositionBucket

    @property
    def on_main_board(self) -> bool:
        return self.bucket == PositionBucket.JOBS


class JobStatusUpdate(BaseSchema):
    ok: bool = Field(default=True)
    applied: bool | None = None
    rejected: bool | None = None
    seen: bool | None = None
    not_for_me: bool | None = None
    looking_to_apply: bool | None = None
    waiting_referral: bool | None = None
    ats_score: int | None = None
    company: str = Field(default="")
    url: str = Field(default="")
    country: str = Field(default="")
