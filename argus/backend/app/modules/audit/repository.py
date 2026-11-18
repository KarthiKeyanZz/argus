"""Audit trail: every consequential action (by user, system or worker) is recorded."""

from __future__ import annotations

from typing import Any, Literal

from psycopg2.extras import Json

from app.db.pool import Cursor
from app.db.sql import Row, fetch_all

Actor = Literal["user", "system", "worker"]

_INSERT = """
INSERT INTO audit_event (actor, action, entity_type, entity_id, details)
VALUES (%(actor)s, %(action)s, %(entity_type)s, %(entity_id)s, %(details)s)
"""

# Keyset pagination on the identity PK (newest first).
# psycopg2 binds parameters client-side, so the planner sees literals and folds
# "NULL IS NULL OR ..." away - optional filters cost nothing and indexes still apply.
_LIST = """
SELECT id, occurred_at, actor, action, entity_type, entity_id, details
FROM audit_event
WHERE (%(action)s::text IS NULL OR action = %(action)s)
  AND (%(entity_type)s::text IS NULL OR entity_type = %(entity_type)s)
  AND (%(entity_id)s::bigint IS NULL OR entity_id = %(entity_id)s)
  AND (%(before_id)s::bigint IS NULL OR id < %(before_id)s)
ORDER BY id DESC
LIMIT %(limit)s
"""


def record(
    cur: Cursor,
    *,
    actor: Actor,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        _INSERT,
        {
            "actor": actor,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": Json(details or {}),
        },
    )


def list_events(
    cur: Cursor,
    *,
    action: str | None,
    entity_type: str | None,
    entity_id: int | None,
    before_id: int | None,
    limit: int,
) -> list[Row]:
    cur.execute(
        _LIST,
        {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before_id": before_id,
            "limit": limit + 1,
        },
    )
    return fetch_all(cur)
