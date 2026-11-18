from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: int
    occurred_at: datetime
    actor: Literal["user", "system", "worker"]
    action: str
    entity_type: str | None
    entity_id: int | None
    details: dict[str, Any]
