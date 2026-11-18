"""CRUD routes for profile sections, generated from one factory.

NOTE: no `from __future__ import annotations` here - FastAPI must see the real model
classes captured by the closure, not string annotations.
"""

from typing import Annotated

import psycopg2
from fastapi import APIRouter, Path, status
from pydantic import BaseModel

from app.api.deps import DbDep
from app.core.exceptions import NotFoundError, UnprocessableError
from app.db.pool import Database
from app.modules.audit import repository as audit
from app.modules.profile import sections
from app.modules.profile.schemas import (
    CertificationIn,
    CertificationOut,
    EducationIn,
    EducationOut,
    ExperienceIn,
    ExperienceOut,
    ProjectIn,
    ProjectOut,
)
from app.shared.schemas import ERROR_RESPONSES

router = APIRouter(prefix="/profile", tags=["profile"], responses=ERROR_RESPONSES)

RowId = Annotated[int, Path(ge=1)]


def _register(
    section: sections.Section, in_model: type[BaseModel], out_model: type[BaseModel]
) -> None:
    path = f"/{section.name}"
    label = section.name.rstrip("s") if section.name != "education" else "education"

    def _get_or_404(db: Database, row_id: int) -> BaseModel:
        with db.transaction() as cur:
            row = sections.get_row(cur, section, row_id)
        if row is None:
            raise NotFoundError(f"{label.title()} {row_id} not found.")
        return out_model.model_validate(row)

    def list_items(db: DbDep) -> list[BaseModel]:
        with db.transaction() as cur:
            return [out_model.model_validate(r) for r in sections.list_rows(cur, section)]

    def create_item(db: DbDep, body: in_model) -> BaseModel:  # type: ignore[valid-type]
        values = body.model_dump()  # type: ignore[attr-defined]
        try:
            with db.transaction() as cur:
                row_id = sections.insert_row(cur, section, values)
                audit.record(
                    cur,
                    actor="user",
                    action=f"{label}.created",
                    entity_type=section.table,
                    entity_id=row_id,
                )
        except psycopg2.errors.CheckViolation as exc:
            raise UnprocessableError(sections.check_violation_message(exc)) from exc
        return _get_or_404(db, row_id)

    def update_item(db: DbDep, row_id: RowId, body: in_model) -> BaseModel:  # type: ignore[valid-type]
        changes = body.model_dump(exclude_unset=True)  # type: ignore[attr-defined]
        try:
            with db.transaction() as cur:
                if changes and not sections.update_row(cur, section, row_id, changes):
                    raise NotFoundError(f"{label.title()} {row_id} not found.")
                audit.record(
                    cur,
                    actor="user",
                    action=f"{label}.updated",
                    entity_type=section.table,
                    entity_id=row_id,
                    details={"fields": sorted(changes)},
                )
        except psycopg2.errors.CheckViolation as exc:
            raise UnprocessableError(sections.check_violation_message(exc)) from exc
        return _get_or_404(db, row_id)

    def delete_item(db: DbDep, row_id: RowId) -> None:
        with db.transaction() as cur:
            if not sections.delete_row(cur, section, row_id):
                raise NotFoundError(f"{label.title()} {row_id} not found.")
            audit.record(
                cur,
                actor="user",
                action=f"{label}.deleted",
                entity_type=section.table,
                entity_id=row_id,
            )

    router.add_api_route(
        path,
        list_items,
        methods=["GET"],
        response_model=list[out_model],  # type: ignore[valid-type]
        name=f"list_{section.name}",
        summary=f"List {section.name}",
    )
    router.add_api_route(
        path,
        create_item,
        methods=["POST"],
        response_model=out_model,
        status_code=status.HTTP_201_CREATED,
        name=f"create_{label}",
        summary=f"Add {label}",
    )
    router.add_api_route(
        f"{path}/{{row_id}}",
        update_item,
        methods=["PUT"],
        response_model=out_model,
        name=f"update_{label}",
        summary=f"Replace {label}",
    )
    router.add_api_route(
        f"{path}/{{row_id}}",
        delete_item,
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        name=f"delete_{label}",
        summary=f"Delete {label}",
    )


_register(sections.SECTIONS["education"], EducationIn, EducationOut)
_register(sections.SECTIONS["experience"], ExperienceIn, ExperienceOut)
_register(sections.SECTIONS["projects"], ProjectIn, ProjectOut)
_register(sections.SECTIONS["certifications"], CertificationIn, CertificationOut)
