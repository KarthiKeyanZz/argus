"""Schemas shared across modules."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class StrictModel(BaseModel):
    """Request bodies: reject unknown fields and trim strings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
    422: {"description": "Validation error"},
}
