"""Company and related schemas."""

from typing import Optional

from pydantic import Field, field_validator

from .common import BaseSchema
from .job import MatchingJob
from .location import Location


class CompanyCreateInput(BaseSchema):
    """Input for creating or updating a company."""

    name: str = Field(..., description="Company name", min_length=1)
    city: Optional[str] = Field(None, description="Single city (legacy, prefer locations)")
    cities: list[str] = Field(default_factory=list, description="List of city names")
    locations: list[Location] = Field(default_factory=list, description="Structured locations")
    size: str = Field(default="", description="Company size (e.g., startup, 500-1000)")
    careers_url: str = Field(default="", description="Career page URL")
    ats_type: str = Field(default="", description="ATS type (e.g., lever, greenhouse)")
    ats_url: str = Field(default="", description="ATS API/endpoint URL")
    fetch_problem: bool = Field(default=False, description="Whether fetching had problems")
    fetch_problem_date: Optional[str] = Field(None, description="Date of fetch problem")
    fetch_ok: bool = Field(default=False, description="Whether fetch succeeded")
    fetch_ok_date: Optional[str] = Field(None, description="Date of successful fetch")
    added: str = Field(default="", description="ISO date when added to catalog")
    updated: str = Field(default="", description="ISO date of last update")
    sources: list[str] = Field(default_factory=list, description="List of data source names")
    matching_jobs: list[MatchingJob] = Field(default_factory=list, description="Jobs from this company")

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Company name cannot be empty")
        return v.strip()


class Company(CompanyCreateInput):
    """A company with full details and job listings."""

    id: Optional[int] = Field(None, description="Database row ID")
    country: Optional[str] = Field(None, description="Country code or name")


class CompanyInDB(BaseSchema):
    """Company as stored in database (mirrors schema rows)."""

    id: int = Field(..., description="Database primary key")
    country: str = Field(...)
    name: str = Field(...)
    city: str = Field(default="")
    size: str = Field(default="")
    careers_url: str = Field(default="")
    ats_type: str = Field(default="")
    ats_url: str = Field(default="")
    fetch_problem: int = Field(default=0, description="0 or 1 (boolean in DB)")
    fetch_problem_date: Optional[str] = Field(None)
    fetch_ok: int = Field(default=0, description="0 or 1 (boolean in DB)")
    fetch_ok_date: Optional[str] = Field(None)
    added: str = Field(default="")
    updated: str = Field(default="")
    sources_json: str = Field(default="[]", description="JSONB column: list of sources")
    cities_json: str = Field(default="[]", description="JSONB column: list of cities")
    locations_json: str = Field(default="[]", description="JSONB column: list of locations")


class CompanyResponse(BaseSchema):
    """Response from company service operations (add, rename, update)."""

    country: str = Field(..., description="Country code")
    country_label: str = Field(..., description="Human-readable country name")
    name: str = Field(..., description="Company name")
    city: str = Field(default="", description="Display city/cities string")
    size: str = Field(default="")
    careers_url: str = Field(default="")
    ats_type: str = Field(default="")
    ats_url: str = Field(default="")
    added: str = Field(default="")
    updated: str = Field(default="")
    sources: list[str] = Field(default_factory=list)
    matching_jobs: list[MatchingJob] = Field(default_factory=list)
