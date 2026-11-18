"""Migration runner safety + proof that hot queries use their indexes."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg2
import pytest

from app.db.migrate import MigrationError, migrate, status

pytestmark = pytest.mark.integration


def test_migrations_are_idempotent(test_dsn: str) -> None:
    assert migrate(test_dsn) == []
    applied, pending = status(test_dsn)
    assert pending == []
    assert "0001_initial_schema" in applied


def test_edited_migration_is_detected(test_dsn: str, migrations_dir: Path, tmp_path: Path) -> None:
    copy = tmp_path / "migrations"
    shutil.copytree(migrations_dir, copy)
    first = sorted(copy.glob("*.sql"))[0]
    first.write_text(first.read_text() + "\n-- sneaky edit\n")
    with pytest.raises(MigrationError, match="modified after being applied"):
        migrate(test_dsn, copy)


@pytest.mark.parametrize(
    ("query", "index"),
    [
        (
            "SELECT id FROM task WHERE status = 'queued' AND run_after <= now() "
            "ORDER BY priority DESC, run_after, id LIMIT 1",
            "task_claim_idx",
        ),
        (
            "SELECT id FROM job WHERE status = 'active' "
            "ORDER BY first_seen_at DESC, id DESC LIMIT 50",
            "job_feed_idx",
        ),
        (
            "SELECT id FROM job WHERE search @@ websearch_to_tsquery('english', 'python')",
            "job_search_gin",
        ),
        ("SELECT id FROM company WHERE name ILIKE '%acme%'", "company_name_trgm"),
        (
            "SELECT job_id FROM job_match WHERE passed_hard_filters ORDER BY score DESC LIMIT 20",
            "job_match_rank_idx",
        ),
    ],
)
def test_hot_queries_use_indexes(clean_db: str, query: str, index: str) -> None:
    conn = psycopg2.connect(clean_db)
    with conn.cursor() as cur:
        # Tables are empty in tests, so force the planner to show which index it *can* use.
        cur.execute("SET enable_seqscan = off")
        cur.execute(f"EXPLAIN {query}")
        plan = "\n".join(row[0] for row in cur.fetchall())
    conn.close()
    assert index in plan, plan


def test_nearest_profile_skill_uses_hnsw_index(clean_db: str) -> None:
    conn = psycopg2.connect(clean_db)
    with conn.cursor() as cur:
        cur.execute("SET enable_seqscan = off")
        vector = "[" + ",".join(["0.1"] * 768) + "]"
        cur.execute(
            "EXPLAIN SELECT normalized_name FROM skill WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> %s::vector LIMIT 1",
            (vector,),
        )
        plan = "\n".join(row[0] for row in cur.fetchall())
    conn.close()
    assert "skill_embedding_hnsw" in plan, plan
