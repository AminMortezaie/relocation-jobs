"""Shared types and utilities for schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
    )


class JSONSerializable(BaseSchema):
    """Base for models that serialize to/from JSON in database."""

    @field_serializer("*", mode="wrap", when_used="json")
    def serialize_model(self, value: Any, _info) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump()
        return value
