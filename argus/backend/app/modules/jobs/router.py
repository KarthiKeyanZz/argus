from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import DbDep
from app.modules.jobs import service
from app.modules.jobs.schemas import JobDetail, JobStatus, JobSummary, ManualJobCreate, WorkMode
from app.modules.tasks.schemas import TaskEnqueued
from app.shared.pagination import CursorParam, LimitParam, Page
from app.shared.schemas import ERROR_RESPONSES

router = APIRouter(prefix="/jobs", tags=["jobs"], responses=ERROR_RESPONSES)

JobId = Annotated[int, Path(ge=1)]


@router.get("", response_model=Page[JobSummary], summary="Job feed (newest first)")
def list_jobs(
    db: DbDep,
    status_: Annotated[JobStatus | None, Query(alias="status")] = "active",
    company_id: Annotated[int | None, Query(ge=1)] = None,
    work_mode: WorkMode | None = None,
    q: Annotated[
        str | None,
        Query(
            min_length=2,
            max_length=200,
            description='Full-text search, web syntax: `python -senior "new grad"`',
        ),
    ] = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[JobSummary]:
    return service.list_page(
        db,
        status=status_,
        company_id=company_id,
        work_mode=work_mode,
        q=q,
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "", response_model=JobDetail, status_code=status.HTTP_201_CREATED, summary="Add a job manually"
)
def create_job(db: DbDep, body: ManualJobCreate) -> JobDetail:
    return service.create_manual(db, body)


@router.get("/{job_id}", response_model=JobDetail, summary="Job details + extracted facts")
def get_job(db: DbDep, job_id: JobId) -> JobDetail:
    return service.get(db, job_id)


@router.post(
    "/{job_id}/extract",
    response_model=TaskEnqueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue LLM extraction of skills / experience for this job",
    description="Runs in the worker (`make worker`). Poll `GET /tasks/{id}`, then "
    "`GET /jobs/{job_id}` shows the `extraction` block.",
)
def extract_job(db: DbDep, job_id: JobId) -> TaskEnqueued:
    return service.request_extraction(db, job_id)


@router.post(
    "/{job_id}/match",
    response_model=TaskEnqueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-score this job against your profile",
    description="Needs an extraction first. Runs automatically after every extraction.",
)
def match_job(db: DbDep, job_id: JobId) -> TaskEnqueued:
    return service.request_match(db, job_id)
