"""FastAPI dependencies. Endpoints declare what they need via these Annotated aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.db.pool import Database
from app.modules.llm.service import LLMService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_db(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


def get_llm(request: Request) -> LLMService:
    return request.app.state.llm  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbDep = Annotated[Database, Depends(get_db)]
LLMDep = Annotated[LLMService, Depends(get_llm)]
