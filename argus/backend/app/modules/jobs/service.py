from __future__ import annotations

from app.core.exceptions import ConflictError, NotFoundError
from app.db.pool import Database
from app.modules.audit import repository as audit
from app.modules.companies import repository as companies
from app.modules.jobs import repository as repo
from app.modules.jobs.schemas import JobDetail, JobSummary, ManualJobCreate
from app.modules.llm.prompts import JOB_EXTRACTION_VERSION
from app.modules.llm.schemas import JobExtractionResponse
from app.modules.tasks import repository as tasks
from app.modules.tasks.kinds import TaskKind
from app.modules.tasks.schemas import TaskEnqueued, TaskOut
from app.shared.pagination import Page, decode_cursor, paginate
from app.shared.text import (
    canonical_url,
    company_key,
    job_dedupe_key,
    normalize_text,
    sha256_hex,
)

MANUAL_SOURCE = "manual"


def list_page(
    db: Database,
    *,
    status: str | None,
    company_id: int | None,
    work_mode: str | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> Page[JobSummary]:
    after = None
    if cursor:
        ts, job_id = decode_cursor(cursor, 2)
        after = (str(ts), int(job_id))
    with db.transaction() as cur:
        rows = repo.list_jobs(
            cur,
            status=status,
            company_id=company_id,
            work_mode=work_mode,
            q=q,
            after=after,
            limit=limit,
        )
    page, next_cursor = paginate(rows, limit, key=lambda r: (r["first_seen_at"], r["id"]))
    return Page(items=[JobSummary.model_validate(r) for r in page], next_cursor=next_cursor)


def get(db: Database, job_id: int) -> JobDetail:
    with db.transaction() as cur:
        row = repo.get_detail(cur, job_id)
    if row is None:
        raise NotFoundError(f"Job {job_id} not found.")
    return JobDetail.model_validate(row)


def create_manual(db: Database, body: ManualJobCreate) -> JobDetail:
    url = canonical_url(str(body.url))
    source_job_id = sha256_hex(url)[:32]  # stable id for a manually added posting
    with db.transaction() as cur:
        company = companies.get_or_create(cur, body.company_name, company_key(body.company_name))
        job_id = repo.insert_job(
            cur,
            {
                "source_kind": MANUAL_SOURCE,
                "company_id": company["id"],
                "source_job_id": source_job_id,
                "title": body.title,
                "title_normalized": normalize_text(body.title),
                "canonical_url": url,
                "apply_url": str(body.apply_url) if body.apply_url else None,
                "location_text": body.location,
                "work_mode": body.work_mode,
                "employment_type": body.employment_type,
                "description_text": body.description,
                "posted_at": body.posted_at,
                "deadline_at": body.deadline_at,
                "content_hash": sha256_hex(body.description),
                "dedupe_key": job_dedupe_key(body.company_name, body.title, body.location),
                "raw": None,
            },
        )
        if job_id is None:
            existing = repo.find_by_source_id(cur, MANUAL_SOURCE, source_job_id)
            raise ConflictError("This job was already added.", details={"job_id": existing})
        audit.record(
            cur, actor="user", action="job.created_manual", entity_type="job", entity_id=job_id
        )
        row = repo.get_detail(cur, job_id)
    if row is None:  # pragma: no cover - inserted in the same transaction
        raise RuntimeError(f"job {job_id} vanished after insert")
    return JobDetail.model_validate(row)


def request_extraction(db: Database, job_id: int) -> TaskEnqueued:
    """Queue LLM extraction for a job; the worker runs it (it can take a while)."""
    with db.transaction() as cur:
        if not repo.exists(cur, job_id):
            raise NotFoundError(f"Job {job_id} not found.")
        row, created = tasks.enqueue(
            cur,
            kind=TaskKind.JOB_EXTRACT,
            payload={"job_id": job_id},
            dedupe_key=f"{TaskKind.JOB_EXTRACT}:{job_id}",
        )
    return TaskEnqueued(task=TaskOut.model_validate(row), created=created)


def request_match(db: Database, job_id: int) -> TaskEnqueued:
    with db.transaction() as cur:
        if not repo.exists(cur, job_id):
            raise NotFoundError(f"Job {job_id} not found.")
        row, created = tasks.enqueue(
            cur,
            kind=TaskKind.MATCH_JOB,
            payload={"job_id": job_id},
            dedupe_key=f"{TaskKind.MATCH_JOB}:{job_id}",
        )
    return TaskEnqueued(task=TaskOut.model_validate(row), created=created)


def save_llm_extraction(db: Database, job_id: int, result: JobExtractionResponse) -> None:
    facts = result.facts
    with db.transaction() as cur:
        repo.upsert_extraction(
            cur,
            {
                "job_id": job_id,
                "method": "llm",
                "model": result.model,
                "extractor_version": JOB_EXTRACTION_VERSION,
                "required_skills": facts.required_skills,
                "preferred_skills": facts.preferred_skills,
                "min_years": facts.min_years_experience,
                "max_years": facts.max_years_experience,
                "education_level": facts.education_level,
                "seniority": facts.seniority,
                "employment_type": facts.employment_type,
                "work_mode": facts.work_mode,
                "entry_level_friendly": facts.entry_level_friendly,
                "summary": facts.summary,
                "education_fields": facts.education_fields,
                "raw": facts.model_dump(),
                "duration_ms": int(result.metrics.total_ms),
            },
        )
        audit.record(
            cur,
            actor="worker",
            action="job.extracted",
            entity_type="job",
            entity_id=job_id,
            details={"model": result.model},
        )
