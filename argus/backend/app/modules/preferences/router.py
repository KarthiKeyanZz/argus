from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.modules.audit import repository as audit
from app.modules.preferences import repository
from app.modules.preferences.schemas import PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesOut, summary="Job-search preferences")
def get_preferences(db: DbDep) -> PreferencesOut:
    with db.transaction() as cur:
        row = repository.get(cur)
    return PreferencesOut.model_validate(row or {})


@router.put("", response_model=PreferencesOut, summary="Replace job-search preferences")
def put_preferences(db: DbDep, body: PreferencesUpdate) -> PreferencesOut:
    values = body.model_dump()
    with db.transaction() as cur:
        row = repository.upsert(cur, values)
        audit.record(
            cur, actor="user", action="preferences.updated", entity_type="preferences", entity_id=1
        )
    return PreferencesOut.model_validate(row)
