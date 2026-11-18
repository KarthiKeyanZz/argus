from __future__ import annotations

import pytest

from app.core.exceptions import UnprocessableError
from app.db.sql import update_by_id
from app.shared.pagination import decode_cursor, encode_cursor, paginate


def test_cursor_round_trip() -> None:
    cursor = encode_cursor("2026-11-13 10:00:00+00:00", 42)
    assert decode_cursor(cursor, 2) == ["2026-11-13 10:00:00+00:00", 42]


@pytest.mark.parametrize("bad", ["***", "e30", encode_cursor(1, 2, 3)])
def test_invalid_cursor(bad: str) -> None:
    with pytest.raises(UnprocessableError):
        decode_cursor(bad, 2)


def test_paginate_uses_extra_row_to_detect_next_page() -> None:
    rows = [{"id": i} for i in (5, 4, 3)]
    page, cursor = paginate(rows, 2, key=lambda r: (r["id"],))
    assert [r["id"] for r in page] == [5, 4]
    assert cursor is not None
    assert decode_cursor(cursor, 1) == [4]

    page, cursor = paginate(rows, 3, key=lambda r: (r["id"],))
    assert len(page) == 3
    assert cursor is None


def test_update_builder_rejects_unknown_columns() -> None:
    with pytest.raises(ValueError, match="not updatable"):
        update_by_id("skill", 1, {"id": 5}, allowed=frozenset({"name"}), returning=("id",))
    with pytest.raises(ValueError, match="no changes"):
        update_by_id("skill", 1, {}, allowed=frozenset({"name"}), returning=("id",))


def test_update_builder_binds_values_as_parameters() -> None:
    statement, params = update_by_id(
        "skill",
        7,
        {"name": "x'; DROP TABLE skill;--"},
        allowed=frozenset({"name"}),
        returning=("id", "name"),
    )
    assert params == {"name": "x'; DROP TABLE skill;--", "_id": 7}
    # the value never appears in the SQL text - only a placeholder does
    assert "DROP" not in repr(statement)
