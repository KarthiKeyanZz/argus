"""PostgreSQL-backed task queue (no Redis needed).

How it works
------------
* ``enqueue`` inserts a row and sends ``NOTIFY argus_tasks`` (delivered on
  commit) so an idle worker wakes immediately instead of polling.
* ``claim`` uses ``FOR UPDATE SKIP LOCKED``: concurrent workers each grab a
  different row without blocking each other. The partial index
  ``task_claim_idx`` (queued rows only, in claim order) makes this O(log n).
* ``dedupe_key`` + a partial unique index guarantees at most one live task per
  key, e.g. one ``job.extract`` per job.
"""

from __future__ import annotations

from typing import Any

from psycopg2.extras import Json

from app.core.exceptions import ConflictError
from app.db.pool import Cursor
from app.db.sql import Row, fetch_all, fetch_one
from app.modules.tasks.kinds import NOTIFY_CHANNEL

_COLUMNS = """id, kind, payload, status, priority, attempts, max_attempts, run_after,
dedupe_key, locked_by, locked_at, result, last_error, created_at, finished_at"""

_ENQUEUE = f"""
INSERT INTO task (kind, payload, priority, max_attempts, run_after, dedupe_key)
VALUES (%(kind)s, %(payload)s, %(priority)s, %(max_attempts)s,
        COALESCE(%(run_after)s, now()), %(dedupe_key)s)
ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL AND status IN ('queued', 'running')
DO NOTHING
RETURNING {_COLUMNS}
"""  # noqa: S608 - constant column list

_FIND_LIVE_BY_DEDUPE = f"""
SELECT {_COLUMNS} FROM task
WHERE dedupe_key = %s AND status IN ('queued', 'running')
"""  # noqa: S608

_CLAIM = f"""
WITH next AS (
    SELECT id FROM task
    WHERE status = 'queued' AND run_after <= now()
    ORDER BY priority DESC, run_after, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE task t
SET status = 'running', locked_by = %(worker)s, locked_at = now(), attempts = t.attempts + 1
FROM next
WHERE t.id = next.id
RETURNING {", ".join("t." + c.strip() for c in _COLUMNS.split(","))}
"""  # noqa: S608

_SUCCEED = """
UPDATE task SET status = 'succeeded', result = %(result)s, finished_at = now(),
                locked_by = NULL, locked_at = NULL, last_error = NULL
WHERE id = %(id)s AND status = 'running'
"""

# Retry with exponential backoff (30s, 60s, 120s, ... capped at 1h) or give up.
# The derived table computes the decision once; the UPDATE applies it.
_FAIL = """
UPDATE task t
SET status      = CASE WHEN d.retry THEN 'queued' ELSE 'failed' END,
    run_after   = CASE WHEN d.retry THEN now() + d.backoff ELSE t.run_after END,
    finished_at = CASE WHEN d.retry THEN NULL ELSE now() END,
    last_error  = left(%(error)s, 2000),
    locked_by   = NULL,
    locked_at   = NULL
FROM (
    SELECT id,
           %(retryable)s AND attempts < max_attempts AS retry,
           LEAST(interval '1 hour', interval '30 seconds' * power(2, attempts - 1)) AS backoff
    FROM task WHERE id = %(id)s
) d
WHERE t.id = d.id AND t.status = 'running'
RETURNING t.status
"""

_CANCEL = f"""
UPDATE task SET status = 'cancelled', finished_at = now()
WHERE id = %s AND status = 'queued'
RETURNING {_COLUMNS}
"""  # noqa: S608

# Tasks whose worker crashed: put them back in the queue (or fail if out of attempts).
_REAP_STALE = """
UPDATE task
SET status     = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
    last_error = 'worker lost (stale lock)',
    finished_at = CASE WHEN attempts < max_attempts THEN NULL ELSE now() END,
    locked_by  = NULL,
    locked_at  = NULL
WHERE status = 'running' AND locked_at < now() - make_interval(secs => %s)
"""

_LIST = f"""
SELECT {_COLUMNS} FROM task
WHERE (%(status)s::text IS NULL OR status = %(status)s)
  AND (%(kind)s::text IS NULL OR kind = %(kind)s)
  AND (%(before_id)s::bigint IS NULL OR id < %(before_id)s)
ORDER BY id DESC
LIMIT %(limit)s
"""  # noqa: S608


def enqueue(
    cur: Cursor,
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    priority: int = 0,
    max_attempts: int = 3,
    run_after: Any = None,
    dedupe_key: str | None = None,
) -> tuple[Row, bool]:
    """Returns ``(task, created)``. If a live task with the same dedupe key exists, returns it."""
    cur.execute(
        _ENQUEUE,
        {
            "kind": kind,
            "payload": Json(payload or {}),
            "priority": priority,
            "max_attempts": max_attempts,
            "run_after": run_after,
            "dedupe_key": dedupe_key,
        },
    )
    row = fetch_one(cur)
    if row is not None:
        cur.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, kind))
        return row, True
    cur.execute(_FIND_LIVE_BY_DEDUPE, (dedupe_key,))
    existing = fetch_one(cur)
    if existing is None:  # the conflicting task finished between the two statements
        raise ConflictError("An identical task just finished; retry the request.")
    return existing, False


def claim(cur: Cursor, worker_id: str) -> Row | None:
    cur.execute(_CLAIM, {"worker": worker_id})
    return fetch_one(cur)


def succeed(cur: Cursor, task_id: int, result: dict[str, Any] | None) -> None:
    cur.execute(_SUCCEED, {"id": task_id, "result": Json(result) if result is not None else None})


def fail(cur: Cursor, task_id: int, error: str, *, retryable: bool) -> str | None:
    cur.execute(_FAIL, {"id": task_id, "error": error, "retryable": retryable})
    row = cur.fetchone()
    return str(row["status"]) if row else None


def cancel(cur: Cursor, task_id: int) -> Row | None:
    cur.execute(_CANCEL, (task_id,))
    return fetch_one(cur)


def reap_stale(cur: Cursor, older_than_s: int) -> int:
    cur.execute(_REAP_STALE, (older_than_s,))
    return int(cur.rowcount)


def get(cur: Cursor, task_id: int) -> Row | None:
    cur.execute(f"SELECT {_COLUMNS} FROM task WHERE id = %s", (task_id,))  # noqa: S608
    return fetch_one(cur)


def list_tasks(
    cur: Cursor, *, status: str | None, kind: str | None, before_id: int | None, limit: int
) -> list[Row]:
    cur.execute(
        _LIST,
        {"status": status, "kind": kind, "before_id": before_id, "limit": limit + 1},
    )
    return fetch_all(cur)
