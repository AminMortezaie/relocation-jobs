"""Pydantic schemas for the relocation jobs catalog.

All database JSON columns use Pydantic models for type-safe serialization/deserialization.
Service request/response schemas ensure type-safe API contracts.
"""

from .common import BaseSchema, JSONSerializable
from .company import Company, CompanyCreateInput, CompanyInDB, CompanyResponse
from .country import CountryCatalog, CountryMeta
from .job import JobLocation, MatchingJob
from .job_response import JobStatusUpdate
from .location import Location

__all__ = [
    "BaseSchema",
    "JSONSerializable",
    "Location",
    "MatchingJob",
    "JobLocation",
    "JobStatusUpdate",
    "Company",
    "CompanyCreateInput",
    "CompanyInDB",
    "CompanyResponse",
    "CountryMeta",
    "CountryCatalog",
]
