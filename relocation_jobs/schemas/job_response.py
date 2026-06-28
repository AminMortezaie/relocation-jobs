"""Job operation response schemas."""

from typing import Optional

from pydantic import Field

from .common import BaseSchema


class JobStatusUpdate(BaseSchema):
    """Response from job status update operations."""

    ok: bool = Field(default=True, description="Operation success")
    applied: Optional[bool] = Field(None, description="Current applied status")
    rejected: Optional[bool] = Field(None, description="Current rejected status")
    seen: Optional[bool] = Field(None, description="Current seen status")
    pinned: Optional[bool] = Field(None, description="Current pinned status")
    board_pinned: Optional[bool] = Field(None, description="Company pinned on board")
    not_for_me: Optional[bool] = Field(None, description="Current not-for-me status")
    looking_to_apply: Optional[bool] = Field(None, description="Current looking-to-apply status")
    waiting_referral: Optional[bool] = Field(None, description="Current waiting-referral status")
    ats_score: Optional[int] = Field(None, description="Current ATS score (0-100)")
    company: str = Field(default="", description="Company name")
    url: str = Field(default="", description="Job URL")
    country: str = Field(default="", description="Country code")
