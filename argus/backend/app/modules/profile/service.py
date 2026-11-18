from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.exceptions import NotFoundError
from app.db.pool import Database
from app.modules.audit import repository as audit
from app.modules.profile import repository as repo
from app.modules.profile.schemas import (
    DataDeletionResult,
    ProfileOut,
    ProfileUpdate,
    SkillBulkCreate,
    SkillBulkResult,
    SkillCreate,
    SkillOut,
    SkillUpdate,
)
from app.shared.text import normalize_skill


def get_profile(db: Database) -> ProfileOut:
    with db.transaction() as cur:
        row = repo.get_profile(cur)
    return ProfileOut.model_validate(row or {})


def replace_profile(db: Database, body: ProfileUpdate) -> ProfileOut:
    values = body.model_dump(mode="json")  # HttpUrl/EmailStr -> plain strings
    values["expected_salary_min"] = body.expected_salary_min  # keep Decimal precision
    values["available_from"] = body.available_from
    with db.transaction() as cur:
        row = repo.upsert_profile(cur, values)
        # never put personal values in the audit log - only which fields are set
        audit.record(
            cur,
            actor="user",
            action="profile.updated",
            entity_type="profile",
            entity_id=1,
            details={"fields_set": sorted(k for k, v in values.items() if v is not None)},
        )
    return ProfileOut.model_validate(row)


# ----------------------------------------------------------------------------- skills


def list_skills(db: Database) -> list[SkillOut]:
    with db.transaction() as cur:
        return [SkillOut.model_validate(r) for r in repo.list_skills(cur)]


def create_skill(db: Database, body: SkillCreate) -> SkillOut:
    values = body.model_dump()
    values["norm"] = normalize_skill(body.name)
    with db.transaction() as cur:
        row = repo.insert_skill(cur, values)
        audit.record(
            cur,
            actor="user",
            action="skill.created",
            entity_type="skill",
            entity_id=row["id"],
            details={"name": row["normalized_name"]},
        )
    return SkillOut.model_validate(row)


def bulk_create_skills(db: Database, body: SkillBulkCreate) -> SkillBulkResult:
    rows = [
        (
            s.name,
            normalize_skill(s.name),
            s.category,
            s.proficiency,
            s.years_experience,
            s.source,
            s.source_ref,
            s.verified,
        )
        for s in body.skills
    ]
    with db.transaction() as cur:
        created = repo.bulk_insert_skills(cur, rows)
        if created:
            audit.record(
                cur, actor="user", action="skill.bulk_created", details={"count": len(created)}
            )
    return SkillBulkResult(
        created=[SkillOut.model_validate(r) for r in created],
        skipped=len(rows) - len(created),
    )


def update_skill(db: Database, skill_id: int, body: SkillUpdate) -> SkillOut:
    changes = body.model_dump(exclude_unset=True)
    with db.transaction() as cur:
        if not changes:
            row = repo.get_skill(cur, skill_id)
        else:
            if "name" in changes:
                changes["normalized_name"] = repo.canonical_skill(
                    cur, normalize_skill(changes["name"])
                )
                changes["embedding"] = None  # re-embedded on the next matching run
            row = repo.update_skill(cur, skill_id, changes)
        if row is None:
            raise NotFoundError(f"Skill {skill_id} not found.")
        if changes:
            audit.record(
                cur,
                actor="user",
                action="skill.updated",
                entity_type="skill",
                entity_id=skill_id,
                details={"fields": sorted(changes)},
            )
    return SkillOut.model_validate(row)


def delete_skill(db: Database, skill_id: int) -> None:
    with db.transaction() as cur:
        if not repo.delete_skill(cur, skill_id):
            raise NotFoundError(f"Skill {skill_id} not found.")
        audit.record(
            cur, actor="user", action="skill.deleted", entity_type="skill", entity_id=skill_id
        )


# ----------------------------------------------------------------------------- export / delete

_PERSONAL_TABLES = (
    "achievement", "education", "experience", "project", "certification", "skill",
    "answer_library", "preferences", "profile",
)  # fmt: skip


def export_all(db: Database) -> dict[str, Any]:
    """Everything ARGUS stores about you, as JSON."""
    from app.modules.preferences import repository as prefs_repo
    from app.modules.profile import sections
    from app.modules.resume import repository as resume_repo

    with db.transaction() as cur:
        data: dict[str, Any] = {
            "profile": repo.get_profile(cur),
            "skills": repo.list_skills(cur),
            "preferences": prefs_repo.get(cur),
            "resumes": resume_repo.list_all(cur),
        }
        for name, section in sections.SECTIONS.items():
            data[name] = sections.list_rows(cur, section)
        audit.record(cur, actor="user", action="data.exported")
    for skill in data["skills"]:
        skill.pop("embedding", None)
    return data


def delete_all(db: Database, data_dir: Path) -> DataDeletionResult:
    """Delete every personal record and uploaded file. Jobs/companies are kept."""
    from app.modules.resume import files

    deleted: dict[str, int] = {}
    with db.transaction() as cur:
        cur.execute("DELETE FROM resume_file RETURNING stored_name")
        stored = [r["stored_name"] for r in cur.fetchall()]
        deleted["resume_file"] = len(stored)
        for table in _PERSONAL_TABLES:
            cur.execute(f"DELETE FROM {table}")  # noqa: S608 - constant table names
            deleted[table] = cur.rowcount
        audit.record(cur, actor="user", action="data.deleted", details=deleted)
    for name in stored:
        files.remove(data_dir, name)
    return DataDeletionResult(deleted=deleted, files_removed=len(stored))
