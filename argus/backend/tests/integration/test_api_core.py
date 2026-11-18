"""Health, security middleware, system pause and audit trail."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_live_and_ready(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json()["status"] == "ok"
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["database"]["ok"] is True
    assert body["migrations"]["ok"] is True
    assert "llm" in body  # informational; mocked host is unreachable in tests


def test_swagger_and_openapi_are_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "ARGUS API"
    operation_ids = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    assert "jobs-list_jobs" in operation_ids
    assert "llm-extract_job" in operation_ids


def test_request_id_and_timing_headers(client: TestClient) -> None:
    r = client.get("/api/v1/health/live", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"
    assert r.headers["Server-Timing"].startswith("app;dur=")
    generated = client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id!"})
    assert generated.headers["X-Request-ID"] != "bad id!"


def test_untrusted_host_is_rejected(client: TestClient) -> None:
    # DNS-rebinding protection: only 127.0.0.1 / localhost are accepted as Host.
    r = client.get("/api/v1/health/live", headers={"Host": "evil.example"})
    assert r.status_code == 400


def test_cross_site_write_is_blocked(client: TestClient) -> None:
    r = client.post("/api/v1/system/pause", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_origin"
    # same-origin (Swagger UI) and the React dev server are allowed
    assert client.post(
        "/api/v1/system/resume", headers={"Origin": "http://127.0.0.1:8000"}
    ).is_success
    assert client.post(
        "/api/v1/system/resume", headers={"Origin": "http://localhost:5173"}
    ).is_success
    # reads are never blocked
    assert client.get("/api/v1/system/state", headers={"Origin": "https://evil.example"}).is_success


def test_pause_resume_is_audited(client: TestClient) -> None:
    paused = client.post("/api/v1/system/pause", json={"reason": "testing"}).json()
    assert paused["paused"] is True
    assert paused["paused_reason"] == "testing"
    assert client.post("/api/v1/system/resume").json()["paused"] is False

    events = client.get("/api/v1/audit-events").json()["items"]
    assert [e["action"] for e in events[:2]] == ["system.resumed", "system.paused"]


def test_error_envelope_shape(client: TestClient) -> None:
    r = client.get("/api/v1/companies/999999")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found"
    assert err["request_id"] == r.headers["X-Request-ID"]


def test_audit_pagination(client: TestClient) -> None:
    for _ in range(3):
        client.post("/api/v1/system/pause")
    first = client.get("/api/v1/audit-events", params={"limit": 2}).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"]
    second = client.get(
        "/api/v1/audit-events", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    ids = [e["id"] for e in first["items"] + second["items"]]
    assert ids == sorted(ids, reverse=True)
