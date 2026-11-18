from __future__ import annotations

from typing import Any

from psycopg2.extras import Json

from app.db.pool import Cursor
from app.db.sql import Row, fetch_one, fetch_required

COLUMNS = (
    "target_titles", "experience_levels", "min_years_experience", "max_years_experience",
    "locations", "countries", "work_modes", "employment_types", "excluded_companies",
    "excluded_keywords", "willing_to_relocate", "min_salary", "salary_currency",
    "scoring_weights", "hard_filters",
)  # fmt: skip
_JSON_COLUMNS = frozenset({"scoring_weights", "hard_filters"})
_SELECT = ", ".join((*COLUMNS, "updated_at"))

_UPSERT = f"""
INSERT INTO preferences (id, {", ".join(COLUMNS)})
VALUES (1, {", ".join(f"%({c})s" for c in COLUMNS)})
ON CONFLICT (id) DO UPDATE SET {", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS)}
RETURNING {_SELECT}
"""  # noqa: S608 - constant column tuple; values are bound parameters


def get(cur: Cursor) -> Row | None:
    cur.execute(f"SELECT {_SELECT} FROM preferences WHERE id = 1")  # noqa: S608
    return fetch_one(cur)


def upsert(cur: Cursor, values: dict[str, Any]) -> Row:
    params = {c: Json(values[c]) if c in _JSON_COLUMNS else values[c] for c in COLUMNS}
    cur.execute(_UPSERT, params)
    row = fetch_required(cur)
    return row
