"""Strict base class for mutable boundary messages."""

from pydantic import BaseModel, ConfigDict


class BoundarySchema(BaseModel):
    """Base schema for input and output messages at application boundaries."""

    model_config = ConfigDict(extra="forbid", validate_default=True)
