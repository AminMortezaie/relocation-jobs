"""Location schemas for companies and jobs."""

from typing import Optional

from pydantic import Field

from .common import BaseSchema


class Location(BaseSchema):
    """A geographic location with country and city."""

    country: str = Field(..., description="ISO country code or full country name")
    city: str = Field(..., description="City name")
