"""Minimal, dependency-free SQL migration runner.

* Migrations are plain ``.sql`` files in ``app/db/migrations`` named
  ``NNNN_description.sql``. They run in filename order, each in its own
  transaction, and are recorded in ``schema_migrations`` with a SHA-256
  checksum.
* An applied migration must never be edited: the runner refuses to continue if
  a checksum changed. Write a new migration instead.
* A PostgreSQL advisory lock prevents two processes migrating at once.

Usage::

    uv run argus-migrate            # apply pending migrations
    uv run argus-migrate status     # show applied / pending
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.pool import Connection, connect_raw

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_ADVISORY_LOCK_KEY = 7_311_942_001  # arbitrary, constant for ARGUS

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    checksum    char(64)    NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    path: Path
    sql: str
    checksum: str


class MigrationError(RuntimeError):
    pass


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=path.stem,
                path=path,
                sql=sql,
                checksum=hashlib.sha256(sql.encode()).hexdigest(),
            )
        )
    return migrations


def _applied(conn: Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(_BOOTSTRAP_SQL)
        cur.execute("SELECT version, checksum FROM schema_migrations")
        rows = cast(list[dict[str, str]], cur.fetchall())  # RealDictCursor rows
        return {row["version"]: row["checksum"] for row in rows}


def pending(conn: Connection, migrations: list[Migration]) -> list[Migration]:
    applied = _applied(conn)
    conn.commit()
    for m in migrations:  # O(n) with dict lookups
        if m.version in applied and applied[m.version] != m.checksum:
            raise MigrationError(
                f"Migration {m.version} was modified after being applied. "
                "Never edit applied migrations; add a new one."
            )
    return [m for m in migrations if m.version not in applied]


def migrate(dsn: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply all pending migrations. Returns the versions applied."""
    conn = connect_raw(dsn, application_name="argus-migrate")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,))
        conn.commit()
        try:
            todo = pending(conn, discover(directory))
            for m in todo:
                logger.info("applying migration %s", m.version)
                with conn.cursor() as cur:
                    cur.execute(m.sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (m.version, m.checksum),
                    )
                conn.commit()
            return [m.version for m in todo]
        except Exception:
            conn.rollback()
            raise
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,))
            conn.commit()
    finally:
        conn.close()


def status(dsn: str, directory: Path = MIGRATIONS_DIR) -> tuple[list[str], list[str]]:
    conn = connect_raw(dsn, application_name="argus-migrate")
    try:
        migrations = discover(directory)
        todo = {m.version for m in pending(conn, migrations)}
        applied = [m.version for m in migrations if m.version not in todo]
        return applied, sorted(todo)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="argus-migrate", description=__doc__.split("\n\n")[0])
    parser.add_argument("command", nargs="?", default="up", choices=["up", "status"])
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    dsn = settings.database_url.get_secret_value()

    if args.command == "status":
        applied, todo = status(dsn)
        print(f"applied ({len(applied)}): {', '.join(applied) or '-'}")
        print(f"pending ({len(todo)}): {', '.join(todo) or '-'}")
        return 0

    done = migrate(dsn)
    print(f"applied {len(done)} migration(s): {', '.join(done) or 'none pending'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
