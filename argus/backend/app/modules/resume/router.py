from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Path, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import DbDep, LLMDep, SettingsDep
from app.core.exceptions import UnprocessableError
from app.modules.resume import files, service
from app.modules.resume.schemas import (
    ResumeDetail,
    ResumeImportRequest,
    ResumeImportResult,
    ResumeOut,
    ResumeParseResponse,
    ResumeUploadResult,
)
from app.shared.schemas import ERROR_RESPONSES

router = APIRouter(prefix="/resumes", tags=["resume"], responses=ERROR_RESPONSES)

ResumeId = Annotated[int, Path(ge=1)]


@router.post(
    "",
    response_model=ResumeUploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a resume (PDF or DOCX, max 5 MB)",
    description="Text is extracted locally. The file never leaves your machine.",
)
async def upload_resume(
    db: DbDep, settings: SettingsDep, file: Annotated[UploadFile, File()]
) -> ResumeUploadResult:
    # Read at most limit+1 bytes so an oversized upload is rejected without buffering it all.
    data = await file.read(files.MAX_UPLOAD_BYTES + 1)
    if len(data) > files.MAX_UPLOAD_BYTES:
        raise UnprocessableError("Resume files must be 5 MB or smaller.")
    # Parsing + DB work is blocking: run it off the event loop.
    return await run_in_threadpool(
        service.upload, db, settings.data_dir, file.filename or "resume", data
    )


@router.get("", response_model=list[ResumeOut], summary="List uploaded resumes")
def list_resumes(db: DbDep) -> list[ResumeOut]:
    return service.list_resumes(db)


@router.get("/{resume_id}", response_model=ResumeDetail, summary="Resume with extracted text")
def get_resume(db: DbDep, resume_id: ResumeId) -> ResumeDetail:
    return service.get(db, resume_id)


@router.delete(
    "/{resume_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a resume and its file"
)
def delete_resume(db: DbDep, settings: SettingsDep, resume_id: ResumeId) -> None:
    service.delete(db, settings.data_dir, resume_id)


@router.post(
    "/{resume_id}/parse",
    response_model=ResumeParseResponse,
    summary="Read the resume with the local LLM (nothing is saved)",
    description="Returns a draft for you to review and edit. Takes ~10-20 s.",
)
def parse_resume(db: DbDep, llm: LLMDep, resume_id: ResumeId) -> ResumeParseResponse:
    return service.parse(db, llm, resume_id)


@router.post(
    "/{resume_id}/import",
    response_model=ResumeImportResult,
    summary="Save the reviewed facts into your profile",
)
def import_resume(db: DbDep, resume_id: ResumeId, body: ResumeImportRequest) -> ResumeImportResult:
    return service.import_facts(db, resume_id, body)
