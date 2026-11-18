"""Keyset (cursor) pagination.

OFFSET pagination makes the database read and throw away every skipped row,
so page N costs O(N * page_size). Keyset pagination remembers the sort key of
the last row and asks for rows *after* it, which an index answers directly:
every page costs O(page_size), no matter how deep you scroll.

The cursor is an opaque base64url-encoded JSON list of the last row's sort key.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, Field

from app.core.exceptions import UnprocessableError

MAX_PAGE_SIZE = 200

LimitParam = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Page size (max 200).")]
CursorParam = Annotated[
    str | None,
    Query(max_length=512, description="Opaque cursor from the previous page's `next_cursor`."),
]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = Field(
        None, description="Pass as `cursor` to fetch the next page. `null` = last page."
    )


def encode_cursor(*values: Any) -> str:
    raw = json.dumps(values, default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, arity: int) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise UnprocessableError("Invalid pagination cursor.") from exc
    if not isinstance(values, list) or len(values) != arity:
        raise UnprocessableError("Invalid pagination cursor.")
    return values


def paginate[T](rows: list[T], limit: int, key: Any) -> tuple[list[T], str | None]:
    """Repositories fetch ``limit + 1`` rows; the extra row tells us a next page exists."""
    if len(rows) <= limit:
        return rows, None
    page = rows[:limit]
    return page, encode_cursor(*key(page[-1]))
