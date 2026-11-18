"""Task queue semantics (claim, retry/backoff, dedupe, concurrency, reaping) and the worker."""

from __future__ import annotations

import json
import select
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg2
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.pool import Database
from app.modules.llm.client import OllamaClient
from app.modules.llm.service import LLMService
from app.modules.tasks import repository as tasks
from app.worker.handlers import TaskContext
from app.worker.main import Worker

pytestmark = pytest.mark.integration


def test_claim_order_and_completion(db: Database) -> None:
    with db.transaction() as cur:
        low, _ = tasks.enqueue(cur, kind="system.ping", priority=0)
        high, _ = tasks.enqueue(cur, kind="system.ping", priority=5)
    with db.transaction() as cur:
        first = tasks.claim(cur, "w1")
    assert first is not None
    assert first["id"] == high["id"]
    assert first["status"] == "running"
    assert first["attempts"] == 1
    with db.transaction() as cur:
        tasks.succeed(cur, first["id"], {"ok": True})
        done = tasks.get(cur, first["id"])
    assert done is not None
    assert done["status"] == "succeeded"
    assert done["result"] == {"ok": True}
    assert low["id"] != high["id"]


def test_retry_backoff_then_give_up(db: Database) -> None:
    with db.transaction() as cur:
        task, _ = tasks.enqueue(cur, kind="system.ping", max_attempts=2)
    with db.transaction() as cur:
        tasks.claim(cur, "w")
        assert tasks.fail(cur, task["id"], "boom", retryable=True) == "queued"
        row = tasks.get(cur, task["id"])
        assert row is not None
        assert row["run_after"] > row["created_at"]  # backoff pushed it into the future
        assert tasks.claim(cur, "w") is None  # not due yet
        cur.execute("UPDATE task SET run_after = now() WHERE id = %s", (task["id"],))
        assert tasks.claim(cur, "w") is not None
        assert tasks.fail(cur, task["id"], "boom again", retryable=True) == "failed"


def test_permanent_failure_is_not_retried(db: Database) -> None:
    with db.transaction() as cur:
        task, _ = tasks.enqueue(cur, kind="system.ping", max_attempts=5)
        tasks.claim(cur, "w")
        assert tasks.fail(cur, task["id"], "bad payload", retryable=False) == "failed"


def test_dedupe_key_allows_new_task_after_completion(db: Database) -> None:
    with db.transaction() as cur:
        a, created_a = tasks.enqueue(cur, kind="system.ping", dedupe_key="k")
        b, created_b = tasks.enqueue(cur, kind="system.ping", dedupe_key="k")
        assert created_a is True
        assert created_b is False
        assert a["id"] == b["id"]
        tasks.claim(cur, "w")
        tasks.succeed(cur, a["id"], None)
        c, created_c = tasks.enqueue(cur, kind="system.ping", dedupe_key="k")
        assert created_c is True
        assert c["id"] != a["id"]


def test_skip_locked_concurrent_claims_never_overlap(db: Database) -> None:
    with db.transaction() as cur:
        for _ in range(20):
            tasks.enqueue(cur, kind="system.ping")

    def claim_all(worker: str) -> list[int]:
        claimed = []
        while True:
            with db.transaction() as cur:
                row = tasks.claim(cur, worker)
            if row is None:
                return claimed
            claimed.append(int(row["id"]))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(claim_all, ["w1", "w2", "w3", "w4"]))
    all_ids = [i for r in results for i in r]
    assert len(all_ids) == 20
    assert len(set(all_ids)) == 20  # every task claimed exactly once


def test_reaper_requeues_stale_tasks(db: Database) -> None:
    with db.transaction() as cur:
        task, _ = tasks.enqueue(cur, kind="system.ping")
        tasks.claim(cur, "dead-worker")
        cur.execute(
            "UPDATE task SET locked_at = now() - interval '2 hours' WHERE id = %s", (task["id"],)
        )
        assert tasks.reap_stale(cur, 3600) == 1
        row = tasks.get(cur, task["id"])
        assert row is not None
        assert row["status"] == "queued"


def test_enqueue_notifies_listeners(db: Database, clean_db: str) -> None:
    listener = psycopg2.connect(clean_db)
    listener.autocommit = True
    with listener.cursor() as cur:
        cur.execute("LISTEN argus_tasks")
    with db.transaction() as cur:
        tasks.enqueue(cur, kind="system.ping")
    deadline = time.monotonic() + 2  # notifications arrive asynchronously over the socket
    while not listener.notifies and time.monotonic() < deadline:
        select.select([listener], [], [], 0.1)
        listener.poll()
    assert [n.payload for n in listener.notifies] == ["system.ping"]
    listener.close()


def test_task_api(client: TestClient) -> None:
    r = client.post("/api/v1/tasks", json={"kind": "system.ping", "payload": {"x": 1}})
    assert r.status_code == 202
    task_id = r.json()["task"]["id"]
    assert client.post("/api/v1/tasks", json={"kind": "job.extract"}).status_code == 422
    assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "queued"
    assert client.post(f"/api/v1/tasks/{task_id}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/v1/tasks/{task_id}/cancel").status_code == 409
    listed = client.get("/api/v1/tasks", params={"status": "cancelled"}).json()["items"]
    assert [t["id"] for t in listed] == [task_id]


# ----------------------------------------------------------------------------- worker


def _worker(db: Database, settings: Settings, dsn: str) -> tuple[Worker, OllamaClient]:
    client = OllamaClient("http://ollama.test", timeout_s=5)
    ctx = TaskContext(db, LLMService(client, settings), settings, "test-worker")
    listen = psycopg2.connect(dsn)
    listen.autocommit = True
    return Worker(ctx, listen), client


def test_worker_runs_ping_and_respects_pause(
    db: Database, settings: Settings, clean_db: str
) -> None:
    worker, client = _worker(db, settings, clean_db)
    with db.transaction() as cur:
        task, _ = tasks.enqueue(cur, kind="system.ping", payload={"hello": "world"})
        cur.execute("UPDATE system_state SET paused = true")
    assert worker._paused() is True
    with db.transaction() as cur:
        cur.execute("UPDATE system_state SET paused = false")

    assert worker._run_one() is True
    assert worker._run_one() is False  # queue empty
    with db.transaction() as cur:
        done = tasks.get(cur, task["id"])
    assert done is not None
    assert done["status"] == "succeeded"
    assert done["result"]["echo"] == {"hello": "world"}
    client.close()
    worker.listen_conn.close()


def test_worker_unknown_kind_fails_permanently(
    db: Database, settings: Settings, clean_db: str
) -> None:
    worker, client = _worker(db, settings, clean_db)
    with db.transaction() as cur:
        task, _ = tasks.enqueue(cur, kind="does.not.exist", max_attempts=5)
    worker._run_one()
    with db.transaction() as cur:
        row = tasks.get(cur, task["id"])
    assert row is not None
    assert row["status"] == "failed"
    assert "no handler" in row["last_error"]
    client.close()
    worker.listen_conn.close()


@respx.mock
def test_worker_job_extract_end_to_end(
    client: TestClient, db: Database, settings: Settings, clean_db: str
) -> None:
    job = client.post(
        "/api/v1/jobs",
        json={
            "company_name": "Acme",
            "title": "Graduate Software Engineer",
            "url": "https://example.com/grad",
            "description": "Graduate role. Requirements: JS, Postgres, Git. Bonus: k8s. "
            "0-1 years. New graduates welcome.",
        },
    ).json()
    client.post(f"/api/v1/jobs/{job['id']}/extract")

    facts = {
        "title": "Graduate Software Engineer", "seniority": "entry",
        "min_years_experience": 0, "max_years_experience": 1, "entry_level_friendly": True,
        "required_skills": ["JS", "Postgres", "git"], "preferred_skills": ["k8s"],
        "education_level": "unknown", "employment_type": "full_time", "work_mode": "unknown",
        "location": None, "summary": "Graduate engineering role.", "education_fields": [],
    }  # fmt: skip
    respx.post("http://ollama.test/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "fake",
                "message": {"content": json.dumps(facts)},
                "eval_count": 10,
                "eval_duration": 100_000_000,
            },
        )
    )
    worker, llm_client = _worker(db, settings, clean_db)
    assert worker._run_one() is True

    extraction = client.get(f"/api/v1/jobs/{job['id']}").json()["extraction"]
    assert extraction["method"] == "llm"
    # canonicalized through skill_alias, order preserved
    assert extraction["required_skills"] == ["javascript", "postgresql", "git"]
    assert extraction["preferred_skills"] == ["kubernetes"]
    assert extraction["entry_level_friendly"] is True
    llm_client.close()
    worker.listen_conn.close()
