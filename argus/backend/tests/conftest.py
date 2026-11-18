"""Test fixtures.

Integration tests run against a separate database, ``argus_test``, in the same
PostgreSQL container (created + migrated automatically). Tables are truncated
before each integration test, so tests are independent. If PostgreSQL is not
running, integration tests are skipped (start it with ``make db-up``).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest
from fastapi.testclient import TestClient
from psycopg2 import sql
from pydantic import SecretStr

from app.core.config import Settings
from app.db.migrate import migrate
from app.db.pool import Database
from app.main import create_app

TEST_DB = "argus_test"
# Reference data seeded by migrations - kept between tests.
_KEEP_TABLES = {"schema_migrations", "source", "skill_alias", "system_state"}


def _with_database(dsn: str, name: str) -> str:
    return urlunsplit(urlsplit(dsn)._replace(path=f"/{name}"))


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    base = Settings()  # type: ignore[call-arg]
    return base.model_copy(
        update={
            "environment": "test",
            "log_level": "WARNING",
            "database_url": SecretStr(
                _with_database(base.database_url.get_secret_value(), TEST_DB)
            ),
            "data_dir": tmp_path_factory.mktemp("argus-data"),
            "ollama_base_url": "http://ollama.test",  # unit tests mock this host
            "worker_idle_wait_s": 0.2,
        }
    )


@pytest.fixture(scope="session")
def test_dsn(settings: Settings) -> str:
    dsn = settings.database_url.get_secret_value()
    admin_dsn = _with_database(dsn, "postgres")
    try:
        admin = psycopg2.connect(admin_dsn, connect_timeout=3)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable (run `make db-up`): {exc}")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))
    admin.close()
    migrate(dsn)
    return dsn


@pytest.fixture(scope="session")
def _truncate_sql(test_dsn: str) -> sql.Composed:
    conn = psycopg2.connect(test_dsn)
    with conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = sorted(r[0] for r in cur.fetchall() if r[0] not in _KEEP_TABLES)
    conn.close()
    return sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
        sql.SQL(", ").join(sql.Identifier(t) for t in tables)
    )


@pytest.fixture
def clean_db(test_dsn: str, _truncate_sql: sql.Composed, settings: Settings) -> str:
    # uploaded files belong to DB rows that are about to be truncated
    shutil.rmtree(settings.data_dir / "resumes", ignore_errors=True)
    conn = psycopg2.connect(test_dsn)
    with conn.cursor() as cur:
        cur.execute(_truncate_sql)
        cur.execute(
            "UPDATE system_state SET paused = false, paused_reason = NULL, paused_at = NULL"
        )
    conn.commit()
    conn.close()
    return test_dsn


@pytest.fixture
def db(settings: Settings, clean_db: str) -> Iterator[Database]:
    database = Database.from_settings(settings, application_name="argus-test")
    yield database
    database.close()


@pytest.fixture
def client(settings: Settings, clean_db: str) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


@pytest.fixture
def migrations_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "app" / "db" / "migrations"
