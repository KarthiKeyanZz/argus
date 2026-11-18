from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, status

from app.api.deps import DbDep, SettingsDep
from app.core.exceptions import UnprocessableError
from app.modules.profile import service
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
from app.shared.schemas import ERROR_RESPONSES

router = APIRouter(prefix="/profile", tags=["profile"], responses=ERROR_RESPONSES)

SkillId = Annotated[int, Path(ge=1)]


@router.get("", response_model=ProfileOut, summary="Get your career profile")
def get_profile(db: DbDep) -> ProfileOut:
    return service.get_profile(db)


@router.put("", response_model=ProfileOut, summary="Create or replace your career profile")
def put_profile(db: DbDep, body: ProfileUpdate) -> ProfileOut:
    return service.replace_profile(db, body)


@router.get("/skills", response_model=list[SkillOut], summary="List skills")
def list_skills(db: DbDep) -> list[SkillOut]:
    return service.list_skills(db)


@router.post(
    "/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED, summary="Add a skill"
)
def create_skill(db: DbDep, body: SkillCreate) -> SkillOut:
    return service.create_skill(db, body)


@router.post(
    "/skills/bulk",
    response_model=SkillBulkResult,
    status_code=status.HTTP_201_CREATED,
    summary="Add many skills in one round-trip",
    description="Existing skills (after synonym mapping, e.g. `JS` = `JavaScript`) are skipped.",
)
def bulk_create_skills(db: DbDep, body: SkillBulkCreate) -> SkillBulkResult:
    return service.bulk_create_skills(db, body)


@router.patch("/skills/{skill_id}", response_model=SkillOut, summary="Update a skill")
def update_skill(db: DbDep, skill_id: SkillId, body: SkillUpdate) -> SkillOut:
    return service.update_skill(db, skill_id, body)


@router.delete(
    "/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a skill"
)
def delete_skill(db: DbDep, skill_id: SkillId) -> None:
    service.delete_skill(db, skill_id)


@router.get(
    "/export",
    summary="Export all your personal data (JSON)",
    description="Profile, skills, sections, preferences and resume metadata.",
)
def export_data(db: DbDep) -> dict[str, Any]:
    return service.export_all(db)


@router.delete(
    "/data",
    response_model=DataDeletionResult,
    summary="Delete ALL personal data and uploaded resumes",
    description="Irreversible. Pass `confirm=DELETE`. Jobs and companies are kept.",
)
def delete_data(
    db: DbDep,
    settings: SettingsDep,
    confirm: Annotated[str, Query(description="Type DELETE to confirm")],
) -> DataDeletionResult:
    if confirm != "DELETE":
        raise UnprocessableError("Pass confirm=DELETE to delete all personal data.")
    return service.delete_all(db, settings.data_dir)
