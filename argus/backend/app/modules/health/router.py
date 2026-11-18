from __future__ import annotations

from typing import Literal

import psycopg2
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app import __version__
from app.api.deps import DbDep, LLMDep
from app.core.exceptions import AppError
from app.db.migrate import discover
from app.modules.llm.client import model_tag

router = APIRouter(prefix="/health", tags=["health"])


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = __version__


class ComponentStatus(BaseModel):
    ok: bool
    detail: str | None = None


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    database: ComponentStatus
    migrations: ComponentStatus
    llm: ComponentStatus = Field(description="Informational: the API works without the LLM.")


@router.get("/live", response_model=Liveness, summary="Process is up")
def live() -> Liveness:
    return Liveness()


@router.get(
    "/ready",
    response_model=Readiness,
    summary="Dependencies are reachable",
    responses={503: {"model": Readiness}},
)
def ready(db: DbDep, llm: LLMDep, response: Response) -> Readiness:
    database = ComponentStatus(ok=db.ping())

    migrations = ComponentStatus(ok=False, detail="database unavailable")
    if database.ok:
        try:
            with db.transaction() as cur:
                cur.execute("SELECT version FROM schema_migrations")
                applied = {r["version"] for r in cur.fetchall()}
            missing = [m.version for m in discover() if m.version not in applied]
            migrations = ComponentStatus(
                ok=not missing, detail=f"pending: {', '.join(missing)}" if missing else None
            )
        except psycopg2.errors.UndefinedTable:
            migrations = ComponentStatus(ok=False, detail="not initialized - run: make migrate")

    try:
        installed = {model_tag(m["name"]) for m in llm.client.list_models()}
        wanted = [llm.settings.llm_chat_model, llm.settings.llm_embed_model]
        absent = [name for name in wanted if model_tag(name) not in installed]
        llm_status = ComponentStatus(
            ok=not absent, detail=f"not installed: {', '.join(absent)}" if absent else None
        )
    except AppError as exc:
        llm_status = ComponentStatus(ok=False, detail=exc.message)

    is_ready = database.ok and migrations.ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(
        status="ready" if is_ready else "not_ready",
        database=database,
        migrations=migrations,
        llm=llm_status,
    )
