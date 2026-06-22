"""Job and matching job schemas."""

from typing import Optional

from pydantic import Field

from .common import BaseSchema
from .location import Location


class JobLocation(BaseSchema):
    """Location information for a job listing."""

    locations: list[Location] = Field(default_factory=list, description="List of job locations")


class MatchingJob(BaseSchema):
    """A job listing from the catalog."""

    title: str = Field(..., description="Job title")
    url: str = Field(..., description="Job URL")
    fetched: str = Field(default="", description="ISO date when job was fetched")
    last_seen: str = Field(default="", description="ISO date when job was last seen")
    idempotency_key: str = Field(default="", description="SHA256 hash of normalized URL")
    visa_sponsorship: Optional[bool] = Field(
        None,
        description="Whether visa sponsorship is available: True, False, or None (unknown)",
    )
    location: str = Field(default="", description="Single location string display")
    locations: list[Location] = Field(default_factory=list, description="Structured locations")
