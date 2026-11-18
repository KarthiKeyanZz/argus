from __future__ import annotations

from app.db.pool import Cursor
from app.db.sql import Row, fetch_one, fetch_required

_COLUMNS = "paused, paused_reason, paused_at, updated_at"

# Upsert keeps working even if the seed row was removed.
_SET_PAUSED = f"""
INSERT INTO system_state (id, paused, paused_reason, paused_at)
VALUES (1, %(paused)s, %(reason)s, CASE WHEN %(paused)s THEN now() END)
ON CONFLICT (id) DO UPDATE
SET paused = EXCLUDED.paused, paused_reason = EXCLUDED.paused_reason, paused_at = EXCLUDED.paused_at
RETURNING {_COLUMNS}
"""  # noqa: S608 - constant column list, no user input


def get_state(cur: Cursor) -> Row:
    cur.execute(f"SELECT {_COLUMNS} FROM system_state WHERE id = 1")  # noqa: S608
    row = fetch_one(cur)
    if row is None:  # seed row missing -> behave as "not paused"
        return set_paused(cur, paused=False, reason=None)
    return row


def is_paused(cur: Cursor) -> bool:
    cur.execute("SELECT paused FROM system_state WHERE id = 1")
    row = cur.fetchone()
    return bool(row and row["paused"])


def set_paused(cur: Cursor, *, paused: bool, reason: str | None) -> Row:
    cur.execute(_SET_PAUSED, {"paused": paused, "reason": reason if paused else None})
    row = fetch_required(cur)
    return row
