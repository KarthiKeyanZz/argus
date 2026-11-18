from __future__ import annotations

from typing import Any

from psycopg2.extras import execute_values

from app.db.pool import Cursor
from app.db.sql import Row, fetch_all, fetch_one, fetch_required

_SUMMARY = (
    "id, original_filename, mime_type, size_bytes, is_master, uploaded_at, "
    "coalesce(length(extracted_text), 0) AS text_chars"
)


def find_by_sha(cur: Cursor, sha256: str) -> Row | None:
    cur.execute(f"SELECT {_SUMMARY} FROM resume_file WHERE sha256 = %s", (sha256,))  # noqa: S608
    return fetch_one(cur)


def insert(cur: Cursor, values: dict[str, Any]) -> Row:
    # The newest upload becomes the master resume (partial unique index allows one).
    cur.execute("UPDATE resume_file SET is_master = false WHERE is_master")
    cur.execute(
        f"""
        INSERT INTO resume_file (original_filename, stored_name, mime_type, size_bytes, sha256,
                                 is_master, extracted_text)
        VALUES (%(original_filename)s, %(stored_name)s, %(mime_type)s, %(size_bytes)s,
                %(sha256)s, true, %(extracted_text)s)
        RETURNING {_SUMMARY}
        """,  # noqa: S608
        values,
    )
    return fetch_required(cur)


def list_all(cur: Cursor) -> list[Row]:
    cur.execute(f"SELECT {_SUMMARY} FROM resume_file ORDER BY id DESC")  # noqa: S608
    return fetch_all(cur)


def get(cur: Cursor, resume_id: int) -> Row | None:
    cur.execute(
        f"SELECT {_SUMMARY}, stored_name, extracted_text FROM resume_file WHERE id = %s",  # noqa: S608
        (resume_id,),
    )
    return fetch_one(cur)


def delete(cur: Cursor, resume_id: int) -> str | None:
    cur.execute("DELETE FROM resume_file WHERE id = %s RETURNING stored_name", (resume_id,))
    row = cur.fetchone()
    return str(row["stored_name"]) if row else None


# ----------------------------------------------------------------------------- import


def delete_imported(cur: Cursor) -> None:
    """Remove facts previously imported from a resume (achievements cascade)."""
    for table in ("education", "experience", "project", "certification"):
        cur.execute(f"DELETE FROM {table} WHERE source = 'resume'")  # noqa: S608 - constant names


def insert_education(cur: Cursor, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    execute_values(
        cur,
        "INSERT INTO education (institution, degree, field_of_study, start_date, end_date, grade, "
        "source, source_ref, verified, sort_order) VALUES %s",
        rows,
    )
    return len(rows)


def insert_experience(cur: Cursor, rows: list[tuple[Any, ...]]) -> dict[int, int]:
    """Returns {sort_order: new id} so achievements can be linked without guessing order."""
    if not rows:
        return {}
    result = execute_values(
        cur,
        "INSERT INTO experience (company, title, employment_type, location, start_date, end_date, "
        "is_current, source, source_ref, verified, sort_order) VALUES %s "
        "RETURNING id, sort_order",
        rows,
        fetch=True,
    )
    return {int(r["sort_order"]): int(r["id"]) for r in result}


def insert_achievements(cur: Cursor, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    execute_values(
        cur,
        "INSERT INTO achievement (experience_id, text, source, source_ref, verified, sort_order) "
        "VALUES %s",
        rows,
    )
    return len(rows)


def insert_projects(cur: Cursor, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    execute_values(
        cur,
        "INSERT INTO project (name, description, url, tech, source, source_ref, verified, "
        "sort_order) VALUES %s",
        rows,
        template="(%s, %s, %s, %s::text[], %s, %s, %s, %s)",
    )
    return len(rows)


def insert_certifications(cur: Cursor, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    execute_values(
        cur,
        "INSERT INTO certification (name, issuer, source, source_ref, verified) VALUES %s",
        rows,
    )
    return len(rows)
