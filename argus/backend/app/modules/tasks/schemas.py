from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.tasks.kinds import TaskKind
from app.shared.schemas import StrictModel

TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class TaskOut(BaseModel):
    id: int
    kind: str
    payload: dict[str, Any]
    status: TaskStatus
    priority: int
    attempts: int
    max_attempts: int
    run_after: datetime
    dedupe_key: str | None
    locked_by: str | None
    locked_at: datetime | None
    result: dict[str, Any] | None
    last_error: str | None
    created_at: datetime
    finished_at: datetime | None


class TaskCreate(StrictModel):
    kind: TaskKind = Field(
        description="Only `system.ping` and `llm.warmup` can be enqueued directly.",
        examples=[TaskKind.SYSTEM_PING],
    )
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(0, ge=-100, le=100)


class TaskEnqueued(BaseModel):
    task: TaskOut
    created: bool = Field(description="False if an identical live task already existed.")
