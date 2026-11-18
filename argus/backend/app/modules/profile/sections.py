"""Generic CRUD for the list-style profile sections (education, experience, projects,
certifications). Table and column names come from the constant SECTIONS registry
and are quoted with ``sql.Identifier``; values are always bound parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2
from psycopg2 import sql

from app.db.pool import Cursor
from app.db.sql import Row, columns, fetch_all, fetch_one, fetch_required, update_by_id

_COMMON = ("source", "source_ref", "verified")


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    table: str
    fields: tuple[str, ...]  # user-editable columns
    order_by: tuple[str, ...] = ("sort_order", "id")
    extra_select: str = ""  # constant SQL fragment (never user input)

    @property
    def writable(self) -> frozenset[str]:
        return frozenset((*self.fields, *_COMMON))

    @property
    def select_list(self) -> sql.Composable:
        base = columns(("id", *self.fields, *_COMMON, "created_at", "updated_at"))
        return sql.SQL("{}{}").format(base, sql.SQL(self.extra_select))


SECTIONS: dict[str, Section] = {
    "education": Section(
        "education", "education",
        ("institution", "degree", "field_of_study", "start_date", "end_date", "grade",
         "sort_order"),
    ),
    "experience": Section(
        "experience", "experience",
        ("company", "title", "employment_type", "location", "start_date", "end_date",
         "is_current", "description", "sort_order"),
        # Bullet points come from the achievement table via its FK index.
        extra_select=(
            ", COALESCE((SELECT array_agg(a.text ORDER BY a.sort_order, a.id) FROM achievement a"
            " WHERE a.experience_id = experience.id), '{}') AS highlights"
        ),
    ),
    "projects": Section(
        "projects", "project",
        ("name", "description", "url", "tech", "start_date", "end_date", "sort_order"),
    ),
    "certifications": Section(
        "certifications", "certification",
        ("name", "issuer", "issued_on", "expires_on", "credential_url"),
        order_by=("id",),
    ),
}  # fmt: skip


def list_rows(cur: Cursor, section: Section) -> list[Row]:
    cur.execute(
        sql.SQL("SELECT {cols} FROM {table} ORDER BY {order}").format(
            cols=section.select_list,
            table=sql.Identifier(section.table),
            order=columns(section.order_by),
        )
    )
    return fetch_all(cur)


def get_row(cur: Cursor, section: Section, row_id: int) -> Row | None:
    cur.execute(
        sql.SQL("SELECT {cols} FROM {table} WHERE id = %s").format(
            cols=section.select_list, table=sql.Identifier(section.table)
        ),
        (row_id,),
    )
    return fetch_one(cur)


def insert_row(cur: Cursor, section: Section, values: dict[str, Any]) -> int:
    names = [k for k in values if k in section.writable]
    cur.execute(
        sql.SQL("INSERT INTO {table} ({cols}) VALUES ({vals}) RETURNING id").format(
            table=sql.Identifier(section.table),
            cols=columns(names),
            vals=sql.SQL(", ").join(sql.Placeholder(n) for n in names),
        ),
        {n: values[n] for n in names},
    )
    return int(fetch_required(cur)["id"])


def update_row(cur: Cursor, section: Section, row_id: int, changes: dict[str, Any]) -> bool:
    statement, params = update_by_id(
        section.table, row_id, changes, allowed=section.writable, returning=("id",)
    )
    cur.execute(statement, params)
    return cur.fetchone() is not None


def delete_row(cur: Cursor, section: Section, row_id: int) -> bool:
    cur.execute(
        sql.SQL("DELETE FROM {table} WHERE id = %s").format(table=sql.Identifier(section.table)),
        (row_id,),
    )
    return bool(cur.rowcount)


def check_violation_message(exc: psycopg2.errors.CheckViolation) -> str:
    return "Invalid values (e.g. end date before start date)."
