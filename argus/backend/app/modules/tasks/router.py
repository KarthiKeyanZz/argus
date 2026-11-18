from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import DbDep
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.modules.audit import repository as audit
from app.modules.tasks import repository
from app.modules.tasks.kinds import USER_ENQUEUEABLE
from app.modules.tasks.schemas import TaskCreate, TaskEnqueued, TaskOut, TaskStatus
from app.shared.pagination import CursorParam, LimitParam, Page, decode_cursor, paginate
from app.shared.schemas import ERROR_RESPONSES

router = APIRouter(prefix="/tasks", tags=["tasks"], responses=ERROR_RESPONSES)

TaskId = Annotated[int, Path(ge=1)]


@router.get("", response_model=Page[TaskOut], summary="List background tasks (newest first)")
def list_tasks(
    db: DbDep,
    status_: Annotated[TaskStatus | None, Query(alias="status")] = None,
    kind: Annotated[str | None, Query(max_length=64)] = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[TaskOut]:
    before_id = int(decode_cursor(cursor, 1)[0]) if cursor else None
    with db.transaction() as cur:
        rows = repository.list_tasks(
            cur, status=status_, kind=kind, before_id=before_id, limit=limit
        )
    page, next_cursor = paginate(rows, limit, key=lambda r: (r["id"],))
    return Page(items=[TaskOut.model_validate(r) for r in page], next_cursor=next_cursor)


@router.get("/{task_id}", response_model=TaskOut, summary="Get one task")
def get_task(db: DbDep, task_id: TaskId) -> TaskOut:
    with db.transaction() as cur:
        row = repository.get(cur, task_id)
    if row is None:
        raise NotFoundError(f"Task {task_id} not found.")
    return TaskOut.model_validate(row)


@router.post(
    "",
    response_model=TaskEnqueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a maintenance task",
    description="Try `system.ping` to verify the worker is running, or `llm.warmup` to load "
    "the chat model into GPU memory before you use it.",
)
def enqueue_task(db: DbDep, body: TaskCreate) -> TaskEnqueued:
    if body.kind not in USER_ENQUEUEABLE:
        raise UnprocessableError(f"Task kind '{body.kind}' cannot be enqueued directly.")
    with db.transaction() as cur:
        row, created = repository.enqueue(
            cur,
            kind=body.kind,
            payload=body.payload,
            priority=body.priority,
            dedupe_key=str(body.kind),  # one live maintenance task of each kind
        )
        if created:
            audit.record(
                cur,
                actor="user",
                action="task.enqueued",
                entity_type="task",
                entity_id=row["id"],
                details={"kind": body.kind},
            )
    return TaskEnqueued(task=TaskOut.model_validate(row), created=created)


@router.post("/{task_id}/cancel", response_model=TaskOut, summary="Cancel a queued task")
def cancel_task(db: DbDep, task_id: TaskId) -> TaskOut:
    with db.transaction() as cur:
        row = repository.cancel(cur, task_id)
        if row is None:
            if repository.get(cur, task_id) is None:
                raise NotFoundError(f"Task {task_id} not found.")
            raise ConflictError("Only queued tasks can be cancelled.")
        audit.record(
            cur, actor="user", action="task.cancelled", entity_type="task", entity_id=task_id
        )
    return TaskOut.model_validate(row)
