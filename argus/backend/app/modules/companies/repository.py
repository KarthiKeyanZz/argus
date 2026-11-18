from __future__ import annotations

from typing import Any

import psycopg2.errors

from app.core.exceptions import ConflictError
from app.db.pool import Cursor
from app.db.sql import Row, fetch_all, fetch_one, fetch_required, update_by_id

COLUMNS = (
    "id", "name", "normalized_key", "website_url", "careers_url", "ats_kind", "ats_token",
    "enabled", "notes", "last_discovered_at", "created_at", "updated_at",
)  # fmt: skip
_SELECT = ", ".join(COLUMNS)
UPDATABLE = frozenset({"name", "normalized_key", "careers_url", "website_url", "enabled", "notes"})

_INSERT = f"""
INSERT INTO company (name, normalized_key, website_url, careers_url, ats_kind, ats_token,
                     enabled, notes)
VALUES (%(name)s, %(normalized_key)s, %(website_url)s, %(careers_url)s, %(ats_kind)s,
        %(ats_token)s, %(enabled)s, %(notes)s)
RETURNING {_SELECT}
"""  # noqa: S608

# Get-or-create in ONE statement. The no-op DO UPDATE makes RETURNING yield the
# existing row on conflict (DO NOTHING would return nothing). No column value
# changes, so the updated_at trigger's WHEN clause leaves updated_at alone.
_GET_OR_CREATE = f"""
INSERT INTO company (name, normalized_key)
VALUES (%(name)s, %(normalized_key)s)
ON CONFLICT (normalized_key) DO UPDATE SET name = company.name
RETURNING {_SELECT}
"""  # noqa: S608

# Keyset pagination on the UNIQUE normalized_key (alphabetical).
# `name ILIKE '%q%'` is served by the trigram GIN index for q >= 3 characters.
_LIST = f"""
SELECT {_SELECT}
FROM company
WHERE (%(enabled)s::boolean IS NULL OR enabled = %(enabled)s)
  AND (%(ats_kind)s::text IS NULL OR ats_kind = %(ats_kind)s)
  AND (%(q)s::text IS NULL OR name ILIKE %(q)s)
  AND (%(after)s::text IS NULL OR normalized_key > %(after)s)
ORDER BY normalized_key
LIMIT %(limit)s
"""  # noqa: S608


def _unique_violation_message(exc: psycopg2.errors.UniqueViolation) -> str:
    constraint = getattr(exc.diag, "constraint_name", "") or ""
    if "ats" in constraint:
        return "A company with this ATS board already exists."
    return "A company with this name already exists."


def insert(cur: Cursor, values: dict[str, Any]) -> Row:
    try:
        cur.execute(_INSERT, values)
    except psycopg2.errors.UniqueViolation as exc:
        raise ConflictError(_unique_violation_message(exc)) from exc
    row = fetch_required(cur)
    return row


def get_or_create(cur: Cursor, name: str, normalized_key: str) -> Row:
    cur.execute(_GET_OR_CREATE, {"name": name, "normalized_key": normalized_key})
    row = fetch_required(cur)
    return row


def get(cur: Cursor, company_id: int) -> Row | None:
    cur.execute(f"SELECT {_SELECT} FROM company WHERE id = %s", (company_id,))  # noqa: S608
    return fetch_one(cur)


def list_companies(
    cur: Cursor,
    *,
    enabled: bool | None,
    ats_kind: str | None,
    q_like: str | None,
    after: str | None,
    limit: int,
) -> list[Row]:
    cur.execute(
        _LIST,
        {"enabled": enabled, "ats_kind": ats_kind, "q": q_like, "after": after, "limit": limit + 1},
    )
    return fetch_all(cur)


def update(cur: Cursor, company_id: int, changes: dict[str, Any]) -> Row | None:
    statement, params = update_by_id(
        "company", company_id, changes, allowed=UPDATABLE, returning=COLUMNS
    )
    try:
        cur.execute(statement, params)
    except psycopg2.errors.UniqueViolation as exc:
        raise ConflictError(_unique_violation_message(exc)) from exc
    return fetch_one(cur)


def delete(cur: Cursor, company_id: int) -> bool:
    try:
        cur.execute("DELETE FROM company WHERE id = %s", (company_id,))
    except psycopg2.errors.ForeignKeyViolation as exc:
        raise ConflictError(
            "This company has job applications; disable it instead of deleting it."
        ) from exc
    return bool(cur.rowcount)
