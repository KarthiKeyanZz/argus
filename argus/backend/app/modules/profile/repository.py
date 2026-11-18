from __future__ import annotations

from typing import Any

import psycopg2.errors
from psycopg2.extras import execute_values

from app.core.exceptions import ConflictError
from app.db.pool import Cursor
from app.db.sql import Row, fetch_all, fetch_one, fetch_required, update_by_id

PROFILE_COLUMNS = (
    "full_name", "email", "phone", "location", "headline", "summary", "linkedin_url",
    "github_url", "portfolio_url", "website_url", "work_authorization", "requires_sponsorship",
    "notice_period", "available_from", "expected_salary_min", "expected_salary_currency",
)  # fmt: skip
_PROFILE_SELECT = ", ".join((*PROFILE_COLUMNS, "updated_at"))

_UPSERT_PROFILE = f"""
INSERT INTO profile (id, {", ".join(PROFILE_COLUMNS)})
VALUES (1, {", ".join(f"%({c})s" for c in PROFILE_COLUMNS)})
ON CONFLICT (id) DO UPDATE SET {", ".join(f"{c} = EXCLUDED.{c}" for c in PROFILE_COLUMNS)}
RETURNING {_PROFILE_SELECT}
"""  # noqa: S608 - built from the constant column tuple above, values are bound parameters

SKILL_COLUMNS = (
    "id", "name", "normalized_name", "category", "proficiency", "years_experience",
    "source", "source_ref", "verified", "created_at", "updated_at",
)  # fmt: skip
_SKILL_SELECT = ", ".join(SKILL_COLUMNS)
SKILL_UPDATABLE = frozenset(
    {
        "name",
        "normalized_name",
        "category",
        "proficiency",
        "years_experience",
        "source_ref",
        "verified",
        "embedding",
    }
)

# Synonym mapping happens in SQL with one indexed lookup per row:
# 'js' -> skill_alias -> 'javascript'. Unknown names map to themselves.
_CANONICAL = "COALESCE((SELECT canonical FROM skill_alias WHERE alias = %(norm)s), %(norm)s)"

_INSERT_SKILL = f"""
INSERT INTO skill (name, normalized_name, category, proficiency, years_experience,
                   source, source_ref, verified)
VALUES (%(name)s, {_CANONICAL}, %(category)s, %(proficiency)s, %(years_experience)s,
        %(source)s, %(source_ref)s, %(verified)s)
RETURNING {_SKILL_SELECT}
"""  # noqa: S608

# Bulk insert: one round-trip for N skills. LEFT JOIN resolves aliases for the whole
# batch via the skill_alias primary key (hash/merge join - not N subqueries).
_BULK_INSERT_SKILLS = f"""
INSERT INTO skill (name, normalized_name, category, proficiency, years_experience,
                   source, source_ref, verified)
SELECT v.name, COALESCE(a.canonical, v.norm), v.category, v.proficiency, v.years,
       v.source, v.source_ref, v.verified
FROM (VALUES %s) AS v(name, norm, category, proficiency, years, source, source_ref, verified)
LEFT JOIN skill_alias a ON a.alias = v.norm
ON CONFLICT (normalized_name) DO NOTHING
RETURNING {_SKILL_SELECT}
"""  # noqa: S608
_BULK_TEMPLATE = (
    "(%s::text, %s::text, %s::text, %s::text, %s::numeric, %s::text, %s::text, %s::boolean)"
)


def get_profile(cur: Cursor) -> Row | None:
    cur.execute(f"SELECT {_PROFILE_SELECT} FROM profile WHERE id = 1")  # noqa: S608
    return fetch_one(cur)


def upsert_profile(cur: Cursor, values: dict[str, Any]) -> Row:
    params = {c: values.get(c) for c in PROFILE_COLUMNS}
    cur.execute(_UPSERT_PROFILE, params)
    row = fetch_required(cur)
    return row


def list_skills(cur: Cursor) -> list[Row]:
    # A personal skill list is small (tens of rows): no pagination needed.
    cur.execute(f"SELECT {_SKILL_SELECT} FROM skill ORDER BY normalized_name")  # noqa: S608
    return fetch_all(cur)


def get_skill(cur: Cursor, skill_id: int) -> Row | None:
    cur.execute(f"SELECT {_SKILL_SELECT} FROM skill WHERE id = %s", (skill_id,))  # noqa: S608
    return fetch_one(cur)


def insert_skill(cur: Cursor, values: dict[str, Any]) -> Row:
    try:
        cur.execute(_INSERT_SKILL, values)
    except psycopg2.errors.UniqueViolation as exc:
        raise ConflictError(f"Skill '{values['name']}' already exists.") from exc
    row = fetch_required(cur)
    return row


def bulk_insert_skills(cur: Cursor, rows: list[tuple[Any, ...]]) -> list[Row]:
    result = execute_values(
        cur, _BULK_INSERT_SKILLS, rows, template=_BULK_TEMPLATE, page_size=500, fetch=True
    )
    return [dict(r) for r in result]


def canonical_skill(cur: Cursor, normalized: str) -> str:
    cur.execute(f"SELECT {_CANONICAL} AS canonical", {"norm": normalized})
    return str(fetch_required(cur)["canonical"])


def update_skill(cur: Cursor, skill_id: int, changes: dict[str, Any]) -> Row | None:
    statement, params = update_by_id(
        "skill", skill_id, changes, allowed=SKILL_UPDATABLE, returning=SKILL_COLUMNS
    )
    try:
        cur.execute(statement, params)
    except psycopg2.errors.UniqueViolation as exc:
        raise ConflictError("Another skill already has that name.") from exc
    return fetch_one(cur)


def delete_skill(cur: Cursor, skill_id: int) -> bool:
    cur.execute("DELETE FROM skill WHERE id = %s", (skill_id,))
    return bool(cur.rowcount)
