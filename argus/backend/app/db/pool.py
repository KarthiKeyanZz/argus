"""PostgreSQL access with psycopg2 and raw SQL - no ORM.

Design notes
------------
* ``ThreadedConnectionPool`` raises ``PoolError`` when exhausted instead of
  waiting. FastAPI runs sync endpoints on a 40-thread pool, so we put a
  ``BoundedSemaphore(max)`` in front of it: callers *wait* (with a timeout)
  for a free connection instead of failing.
* The pool is created lazily, so the API can start (and report "not ready")
  while the database container is still booting.
* ``transaction()`` is the unit of work: one connection, one transaction,
  commit on success, rollback on error. Hold it only while running SQL -
  never across slow calls such as LLM requests.
* Rows come back as dicts (``RealDictCursor``) and are validated by Pydantic
  schemas at the API boundary.
* All values are passed as parameters (``%s`` / ``%(name)s``). Building SQL
  with f-strings is forbidden (ruff rule S608). Dynamic identifiers use
  ``psycopg2.sql`` composition.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import psycopg2
import psycopg2.extensions
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

Cursor = psycopg2.extras.RealDictCursor
Connection = psycopg2.extensions.connection


class Database:
    def __init__(
        self,
        dsn: str,
        *,
        idle: int = 4,
        maximum: int = 10,
        acquire_timeout_s: float = 10.0,
        statement_timeout_ms: int = 15_000,
        application_name: str = "argus-api",
    ) -> None:
        self._dsn = dsn
        self._idle = min(idle, maximum)
        self._max = maximum
        self._acquire_timeout_s = acquire_timeout_s
        self._connect_kwargs = {
            "cursor_factory": psycopg2.extras.RealDictCursor,
            "application_name": application_name,
            "options": f"-c statement_timeout={int(statement_timeout_ms)}",
            "connect_timeout": 5,
        }
        self._pool: ThreadedConnectionPool | None = None
        self._pool_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(maximum)

    @classmethod
    def from_settings(cls, settings: Settings, application_name: str = "argus-api") -> Database:
        return cls(
            settings.database_url.get_secret_value(),
            idle=settings.db_pool_idle,
            maximum=settings.db_pool_max,
            acquire_timeout_s=settings.db_pool_acquire_timeout_s,
            statement_timeout_ms=settings.db_statement_timeout_ms,
            application_name=application_name,
        )

    # ------------------------------------------------------------------ pool
    def _get_pool(self) -> ThreadedConnectionPool:
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:  # double-checked locking
                    # minconn=0 -> lazy connect; idle connections are kept up to `idle`
                    # by our own putconn logic below.
                    self._pool = ThreadedConnectionPool(
                        0, self._max, self._dsn, **self._connect_kwargs
                    )
                    self._pool.minconn = self._idle  # psycopg2 keeps up to minconn idle
        return self._pool

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        if not self._slots.acquire(timeout=self._acquire_timeout_s):
            raise ServiceUnavailableError("Database connection pool is saturated; retry later.")
        pool = self._get_pool()
        conn: Connection | None = None
        broken = False
        try:
            conn = pool.getconn()
            yield conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            broken = True
            raise
        finally:
            if conn is not None:
                pool.putconn(conn, close=broken or bool(conn.closed))
            self._slots.release()

    @contextmanager
    def transaction(self) -> Iterator[Cursor]:
        """One connection + one transaction. Commits on success, rolls back on error."""
        with self.connection() as conn:
            try:
                with cast(Cursor, conn.cursor()) as cur:
                    yield cur
                conn.commit()
            except BaseException:
                if not conn.closed:
                    try:
                        conn.rollback()
                    except psycopg2.Error:
                        logger.warning("rollback failed; connection will be discarded")
                raise

    def ping(self) -> bool:
        try:
            with self.transaction() as cur:
                cur.execute("SELECT 1 AS ok")
                return bool(cur.fetchone())
        except (psycopg2.Error, ServiceUnavailableError):
            return False

    def close(self) -> None:
        with self._pool_lock:
            if self._pool is not None and not self._pool.closed:
                self._pool.closeall()
            self._pool = None


def connect_raw(
    dsn: str, *, autocommit: bool = False, application_name: str = "argus"
) -> Connection:
    """A standalone connection (migrations, worker LISTEN channel)."""
    conn = psycopg2.connect(
        dsn,
        cursor_factory=psycopg2.extras.RealDictCursor,
        application_name=application_name,
        connect_timeout=5,
    )
    conn.autocommit = autocommit
    return conn
