from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.modules.audit import repository as audit
from app.modules.system import repository
from app.modules.system.schemas import PauseRequest, SystemStateOut

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/state", response_model=SystemStateOut, summary="Global run state")
def get_state(db: DbDep) -> SystemStateOut:
    with db.transaction() as cur:
        return SystemStateOut.model_validate(repository.get_state(cur))


@router.post(
    "/pause",
    response_model=SystemStateOut,
    summary="Pause all automation (global stop)",
    description="The worker stops picking up tasks. "
    "Tasks already running finish their current step.",
)
def pause(db: DbDep, body: PauseRequest | None = None) -> SystemStateOut:
    reason = body.reason if body else None
    with db.transaction() as cur:
        state = repository.set_paused(cur, paused=True, reason=reason)
        audit.record(cur, actor="user", action="system.paused", details={"reason": reason})
    return SystemStateOut.model_validate(state)


@router.post("/resume", response_model=SystemStateOut, summary="Resume automation")
def resume(db: DbDep) -> SystemStateOut:
    with db.transaction() as cur:
        state = repository.set_paused(cur, paused=False, reason=None)
        audit.record(cur, actor="user", action="system.resumed")
    return SystemStateOut.model_validate(state)
