from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.shared.schemas import StrictModel


class SystemStateOut(StrictModel):
    paused: bool = Field(description="When true, the worker runs no tasks (global kill switch).")
    paused_reason: str | None
    paused_at: datetime | None
    updated_at: datetime


class PauseRequest(StrictModel):
    reason: str | None = Field(None, max_length=500, examples=["Reviewing results"])
