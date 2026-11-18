"""Background worker: claims tasks from PostgreSQL and runs their handlers.

Wake-up strategy
----------------
* The API sends ``NOTIFY argus_tasks`` when it enqueues, so an idle worker
  starts within milliseconds - no busy polling.
* Delayed tasks (retries with backoff) don't produce a NOTIFY, so the worker
  also re-checks the queue at least every ``worker_idle_wait_s`` seconds.
* The global pause flag is checked before every claim.

Run: ``make worker``  (stop with Ctrl+C; the current task finishes first).
"""

from __future__ import annotations

import logging
import os
import select
import signal
import socket
import sys
import time
from types import FrameType

from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError, UnprocessableError
from app.core.logging import configure_logging, request_id_ctx
from app.db.pool import Connection, Database, connect_raw
from app.modules.llm.client import OllamaClient
from app.modules.llm.service import LLMService
from app.modules.system import repository as system_repo
from app.modules.tasks import repository as tasks_repo
from app.modules.tasks.kinds import NOTIFY_CHANNEL
from app.worker.handlers import HANDLERS, PermanentTaskError, TaskContext

logger = logging.getLogger("argus.worker")

_REAP_EVERY_S = 60.0
_SLICE_S = 1.0  # max latency for noticing Ctrl+C while idle


class Worker:
    def __init__(self, ctx: TaskContext, listen_conn: Connection) -> None:
        self.ctx = ctx
        self.listen_conn = listen_conn
        self.stopping = False
        self._last_reap = 0.0

    # ------------------------------------------------------------------ lifecycle
    def request_stop(self, signum: int, _frame: FrameType | None) -> None:
        logger.info(
            "received %s - finishing current task, then stopping", signal.Signals(signum).name
        )
        self.stopping = True

    def run(self) -> None:
        with self.listen_conn.cursor() as cur:
            cur.execute(f"LISTEN {NOTIFY_CHANNEL}")
        logger.info("worker %s listening on '%s'", self.ctx.worker_id, NOTIFY_CHANNEL)
        while not self.stopping:
            self._maybe_reap()
            if self._paused():
                self._wait(self.ctx.settings.worker_idle_wait_s)
                continue
            if not self._run_one():
                self._wait(self.ctx.settings.worker_idle_wait_s)
        logger.info("worker stopped")

    # ------------------------------------------------------------------ steps
    def _paused(self) -> bool:
        with self.ctx.db.transaction() as cur:
            return system_repo.is_paused(cur)

    def _maybe_reap(self) -> None:
        now = time.monotonic()
        if now - self._last_reap < _REAP_EVERY_S:
            return
        self._last_reap = now
        with self.ctx.db.transaction() as cur:
            count = tasks_repo.reap_stale(cur, self.ctx.settings.worker_stale_task_after_s)
        if count:
            logger.warning("re-queued %d stale task(s)", count)

    def _run_one(self) -> bool:
        """Claim and run one task. Returns False when the queue is empty."""
        with self.ctx.db.transaction() as cur:
            task = tasks_repo.claim(cur, self.ctx.worker_id)
        if task is None:
            return False

        task_id, kind = int(task["id"]), str(task["kind"])
        token = request_id_ctx.set(f"task-{task_id}")
        started = time.perf_counter()
        try:
            handler = HANDLERS.get(kind)
            if handler is None:
                raise PermanentTaskError(f"no handler for task kind '{kind}'")
            result = handler(self.ctx, dict(task["payload"] or {}))
            with self.ctx.db.transaction() as cur:
                tasks_repo.succeed(cur, task_id, result)
            logger.info(
                "task %d %s succeeded in %.0f ms",
                task_id,
                kind,
                (time.perf_counter() - started) * 1000,
            )
        except (PermanentTaskError, NotFoundError, UnprocessableError) as exc:
            self._fail(task_id, kind, str(exc), retryable=False)
        except AppError as exc:
            self._fail(task_id, kind, exc.message, retryable=True)
        except Exception as exc:
            logger.exception("task %d %s crashed", task_id, kind)
            self._fail(task_id, kind, f"{type(exc).__name__}: {exc}", retryable=True)
        finally:
            request_id_ctx.reset(token)
        return True

    def _fail(self, task_id: int, kind: str, error: str, *, retryable: bool) -> None:
        with self.ctx.db.transaction() as cur:
            new_status = tasks_repo.fail(cur, task_id, error, retryable=retryable)
        logger.warning(
            "task %d %s failed (%s): %s",
            task_id,
            kind,
            "will retry" if new_status == "queued" else "giving up",
            error,
        )

    def _wait(self, timeout_s: float) -> None:
        """Sleep until a NOTIFY arrives, the timeout passes, or a stop is requested."""
        deadline = time.monotonic() + timeout_s
        while not self.stopping:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            readable, _, _ = select.select([self.listen_conn], [], [], min(_SLICE_S, remaining))
            if readable:
                self.listen_conn.poll()
                if self.listen_conn.notifies:
                    self.listen_conn.notifies.clear()
                    return


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    dsn = settings.database_url.get_secret_value()

    db = Database.from_settings(settings, application_name="argus-worker")
    client = OllamaClient(settings.ollama_base_url, timeout_s=settings.llm_request_timeout_s)
    listen_conn = connect_raw(dsn, autocommit=True, application_name="argus-worker-listen")
    worker = Worker(TaskContext(db, LLMService(client, settings), settings, worker_id), listen_conn)

    signal.signal(signal.SIGINT, worker.request_stop)
    signal.signal(signal.SIGTERM, worker.request_stop)
    try:
        worker.run()
    finally:
        listen_conn.close()
        client.close()
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
