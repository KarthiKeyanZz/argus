from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DbDep
from app.modules.matching import service
from app.modules.matching.schemas import ShortlistItem
from app.modules.tasks import repository as tasks
from app.modules.tasks.kinds import TaskKind
from app.modules.tasks.schemas import TaskEnqueued, TaskOut
from app.shared.pagination import CursorParam, LimitParam, Page

router = APIRouter(prefix="/matching", tags=["matching"])


@router.post(
    "/run",
    response_model=TaskEnqueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-score every active job",
    description="Run after changing your profile, skills or preferences. Executed by the worker.",
)
def run_matching(db: DbDep) -> TaskEnqueued:
    with db.transaction() as cur:
        row, created = tasks.enqueue(cur, kind=TaskKind.MATCH_ALL, dedupe_key=TaskKind.MATCH_ALL)
    return TaskEnqueued(task=TaskOut.model_validate(row), created=created)


@router.get(
    "/shortlist",
    response_model=Page[ShortlistItem],
    summary="Best matches first",
    description="Jobs ranked by fit score. By default only jobs that pass every hard filter.",
)
def shortlist(
    db: DbDep,
    include_failed: bool = False,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[ShortlistItem]:
    return service.shortlist_page(db, include_failed=include_failed, limit=limit, cursor=cursor)
