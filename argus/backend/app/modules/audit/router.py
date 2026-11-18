from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.modules.audit import repository
from app.modules.audit.schemas import AuditEventOut
from app.shared.pagination import CursorParam, LimitParam, Page, decode_cursor, paginate

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=Page[AuditEventOut], summary="List audit events (newest first)")
def list_audit_events(
    db: DbDep,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[int | None, Query(ge=1)] = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[AuditEventOut]:
    before_id = int(decode_cursor(cursor, 1)[0]) if cursor else None
    with db.transaction() as cur:
        rows = repository.list_events(
            cur,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_id=before_id,
            limit=limit,
        )
    page, next_cursor = paginate(rows, limit, key=lambda r: (r["id"],))
    return Page(items=[AuditEventOut.model_validate(r) for r in page], next_cursor=next_cursor)
