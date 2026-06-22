"""Country and country metadata schemas."""

from typing import Optional

from pydantic import Field

from .common import BaseSchema
from .company import Company


class CountryMeta(BaseSchema):
    """Metadata about a country's catalog."""

    country: str = Field(..., description="Country code or name")
    source: str = Field(default="", description="Source of company data")
    fetched: str = Field(default="", description="ISO date when jobs were fetched")
    updated: str = Field(default="", description="ISO date of last catalog update")
    jobs_fetched: str = Field(default="", description="ISO date when jobs were last fetched")
    total: int = Field(default=0, description="Total number of companies")
    last_fetch_new_jobs: int = Field(default=0, description="Number of new jobs in last fetch")


class CountryCatalog(BaseSchema):
    """Complete catalog for a country with metadata and companies."""

    source: str = Field(default="")
    fetched: str = Field(default="")
    updated: str = Field(default="")
    jobs_fetched: str = Field(default="")
    total: int = Field(default=0)
    last_fetch_new_jobs: int = Field(default=0)
    companies: list[Company] = Field(default_factory=list)
