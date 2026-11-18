"""Task handlers. Each takes (context, payload) and returns a JSON-able result dict.

Raise ``PermanentTaskError`` for failures that retrying cannot fix; any other
exception is treated as transient and retried with exponential backoff.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.db.pool import Database
from app.modules.jobs import repository as jobs_repo
from app.modules.jobs import service as jobs_service
from app.modules.llm.schemas import JobExtractionRequest, LLMOptions
from app.modules.llm.service import LLMService
from app.modules.matching import service as matching_service
from app.modules.tasks.kinds import TaskKind


class PermanentTaskError(Exception):
    """Do not retry (bad payload, missing entity, ...)."""


@dataclass(frozen=True, slots=True)
class TaskContext:
    db: Database
    llm: LLMService
    settings: Settings
    worker_id: str


Handler = Callable[[TaskContext, dict[str, Any]], dict[str, Any] | None]


def system_ping(ctx: TaskContext, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "pong": True,
        "worker": ctx.worker_id,
        "at": datetime.now(UTC).isoformat(),
        "echo": payload,
    }


def llm_warmup(ctx: TaskContext, _: dict[str, Any]) -> dict[str, Any]:
    metrics = ctx.llm.warmup()
    return {
        "model": ctx.settings.llm_chat_model,
        "load_ms": metrics.load_ms,
        "total_ms": metrics.total_ms,
    }


def job_extract(ctx: TaskContext, payload: dict[str, Any]) -> dict[str, Any]:
    job_id = payload.get("job_id")
    if not isinstance(job_id, int):
        raise PermanentTaskError("payload.job_id must be an integer")

    # 1) short transaction to read the job ...
    with ctx.db.transaction() as cur:
        job = jobs_repo.get_text_for_extraction(cur, job_id)
    if job is None:
        raise PermanentTaskError(f"job {job_id} no longer exists")

    # 2) ... the slow LLM call happens with NO database connection held ...
    text = "\n".join(filter(None, (job["title"], job["location_text"], job["description_text"])))
    if len(text) < 50:
        raise PermanentTaskError("job description too short to extract from")
    result = ctx.llm.extract_job(
        JobExtractionRequest(
            text=text[:60_000], options=LLMOptions(temperature=0, seed=7), think=False
        )
    )

    # 3) ... then a second short transaction to save the result, and queue scoring.
    jobs_service.save_llm_extraction(ctx.db, job_id, result)
    jobs_service.request_match(ctx.db, job_id)
    return {
        "job_id": job_id,
        "model": result.model,
        "required_skills": len(result.facts.required_skills),
        "output_tokens_per_s": result.metrics.output_tokens_per_s,
        "total_ms": result.metrics.total_ms,
    }


def match_job(ctx: TaskContext, payload: dict[str, Any]) -> dict[str, Any]:
    job_id = payload.get("job_id")
    if not isinstance(job_id, int):
        raise PermanentTaskError("payload.job_id must be an integer")
    return matching_service.score_jobs(ctx.db, ctx.llm, job_ids=[job_id])


def match_all(ctx: TaskContext, _: dict[str, Any]) -> dict[str, Any]:
    return matching_service.score_jobs(ctx.db, ctx.llm)


HANDLERS: dict[str, Handler] = {
    TaskKind.SYSTEM_PING: system_ping,
    TaskKind.LLM_WARMUP: llm_warmup,
    TaskKind.JOB_EXTRACT: job_extract,
    TaskKind.MATCH_JOB: match_job,
    TaskKind.MATCH_ALL: match_all,
}
