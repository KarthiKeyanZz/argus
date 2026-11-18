"""Mounts every module router under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.audit.router import router as audit_router
from app.modules.companies.router import router as companies_router
from app.modules.health.router import router as health_router
from app.modules.jobs.router import router as jobs_router
from app.modules.llm.router import router as llm_router
from app.modules.matching.router import router as matching_router
from app.modules.preferences.router import router as preferences_router
from app.modules.profile.router import router as profile_router
from app.modules.profile.sections_router import router as sections_router
from app.modules.resume.router import router as resume_router
from app.modules.system.router import router as system_router
from app.modules.tasks.router import router as tasks_router

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
for module_router in (
    health_router,
    profile_router,
    sections_router,
    resume_router,
    preferences_router,
    companies_router,
    jobs_router,
    matching_router,
    llm_router,
    tasks_router,
    system_router,
    audit_router,
):
    api_router.include_router(module_router)
