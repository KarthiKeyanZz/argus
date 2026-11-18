"""Small helpers for raw-SQL repositories."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from psycopg2 import sql

from app.db.pool import Cursor

Row = dict[str, Any]


def fetch_one(cur: Cursor) -> Row | None:
    row = cur.fetchone()
    return dict(row) if row is not None else None


def fetch_required(cur: Cursor) -> Row:
    """For statements that always return a row (INSERT/UPSERT ... RETURNING)."""
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("statement unexpectedly returned no row")
    return dict(row)


def fetch_all(cur: Cursor) -> list[Row]:
    return [dict(r) for r in cur.fetchall()]


def columns(names: Iterable[str]) -> sql.Composed:
    """``a, b, c`` as safely quoted identifiers."""
    return sql.SQL(", ").join(sql.Identifier(n) for n in names)


def update_by_id(
    table: str,
    row_id: int,
    changes: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    returning: Sequence[str],
) -> tuple[sql.Composed, dict[str, Any]]:
    """Build ``UPDATE <table> SET col = %(col)s, ... WHERE id = %(_id)s RETURNING ...``.

    Only whitelisted column names are accepted, and they are quoted with
    ``sql.Identifier`` - values are always bound parameters, never interpolated.
    """
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"not updatable on {table}: {sorted(unknown)}")
    if not changes:
        raise ValueError("no changes")
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = {}").format(sql.Identifier(col), sql.Placeholder(col)) for col in changes
    )
    statement = sql.SQL(
        "UPDATE {table} SET {assignments} WHERE id = %(_id)s RETURNING {ret}"
    ).format(
        table=sql.Identifier(table),
        assignments=assignments,
        ret=columns(returning),
    )
    params = {**changes, "_id": row_id}
    return statement, params


def as_text(composed: sql.Composable, cur: Cursor) -> str:
    """Render composed SQL (useful in tests / EXPLAIN)."""
    return composed.as_string(cur)
