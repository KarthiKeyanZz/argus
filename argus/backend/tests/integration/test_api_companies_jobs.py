"""Companies (ATS detection, search, keyset paging) and jobs (manual add, feed, extraction)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

DESCRIPTION = (
    "We are hiring a junior backend engineer. Requirements: Python, SQL, REST APIs, Git. "
    "0-2 years of experience. Freshers welcome. Nice to have: Docker."
)


def _job(**overrides: object) -> dict[str, object]:
    return {
        "company_name": "Acme Analytics Pvt Ltd",
        "title": "Junior Backend Engineer",
        "url": "https://example.com/careers/123?utm_source=newsletter",
        "location": "Bengaluru",
        "work_mode": "hybrid",
        "description": DESCRIPTION,
        **overrides,
    }


def test_create_company_detects_ats(client: TestClient) -> None:
    r = client.post(
        "/api/v1/companies",
        json={"name": "Stripe, Inc.", "careers_url": "https://job-boards.greenhouse.io/Stripe"},
    )
    assert r.status_code == 201
    body = r.json()
    assert (body["ats_kind"], body["ats_token"], body["normalized_key"]) == (
        "greenhouse",
        "stripe",
        "stripe",
    )


def test_company_conflicts(client: TestClient) -> None:
    client.post(
        "/api/v1/companies", json={"name": "Ramp", "careers_url": "https://jobs.ashbyhq.com/ramp"}
    )
    same_name = client.post("/api/v1/companies", json={"name": "RAMP Inc"})
    assert same_name.status_code == 409
    same_board = client.post(
        "/api/v1/companies",
        json={"name": "Ramp Two", "careers_url": "https://jobs.ashbyhq.com/ramp"},
    )
    assert same_board.status_code == 409
    assert "ATS board" in same_board.json()["error"]["message"]


def test_detect_ats_endpoint(client: TestClient) -> None:
    r = client.post("/api/v1/companies/detect-ats", json={"url": "https://jobs.lever.co/palantir"})
    assert r.json() == {"detected": True, "ats_kind": "lever", "ats_token": "palantir"}
    r = client.post("/api/v1/companies/detect-ats", json={"url": "https://example.com/careers"})
    assert r.json()["detected"] is False


def test_company_list_search_and_keyset_paging(client: TestClient) -> None:
    for name in ("Delta", "alpha", "Charlie", "Bravo", "Echo 100%"):
        client.post("/api/v1/companies", json={"name": name})
    page1 = client.get("/api/v1/companies", params={"limit": 2}).json()
    page2 = client.get(
        "/api/v1/companies", params={"limit": 2, "cursor": page1["next_cursor"]}
    ).json()
    page3 = client.get(
        "/api/v1/companies", params={"limit": 2, "cursor": page2["next_cursor"]}
    ).json()
    names = [c["name"] for p in (page1, page2, page3) for c in p["items"]]
    assert names == ["alpha", "Bravo", "Charlie", "Delta", "Echo 100%"]
    assert page3["next_cursor"] is None

    found = client.get("/api/v1/companies", params={"q": "arl"}).json()["items"]
    assert [c["name"] for c in found] == ["Charlie"]
    # LIKE wildcards in user input are matched literally
    assert [
        c["name"] for c in client.get("/api/v1/companies", params={"q": "%"}).json()["items"]
    ] == ["Echo 100%"]


def test_company_update_and_delete(client: TestClient) -> None:
    company = client.post("/api/v1/companies", json={"name": "Foxtrot"}).json()
    updated = client.patch(f"/api/v1/companies/{company['id']}", json={"enabled": False})
    assert updated.json()["enabled"] is False
    assert (
        client.patch(f"/api/v1/companies/{company['id']}", json={"enabled": None}).status_code
        == 422
    )
    assert client.delete(f"/api/v1/companies/{company['id']}").status_code == 204
    assert client.get(f"/api/v1/companies/{company['id']}").status_code == 404


def test_manual_job_create_dedupes_and_reuses_company(client: TestClient) -> None:
    created = client.post("/api/v1/jobs", json=_job())
    assert created.status_code == 201
    job = created.json()
    assert job["source"] == "manual"
    assert job["company_name"] == "Acme Analytics Pvt Ltd"
    assert job["canonical_url"] == "https://example.com/careers/123"  # tracking param removed
    assert job["extraction"] is None

    again = client.post("/api/v1/jobs", json=_job(url="https://example.com/careers/123/"))
    assert again.status_code == 409
    assert again.json()["error"]["details"]["job_id"] == job["id"]

    other = client.post(
        "/api/v1/jobs", json=_job(company_name="ACME ANALYTICS", url="https://example.com/x")
    )
    assert other.json()["company_id"] == job["company_id"]  # same normalized company
    assert other.json()["duplicate_of"] == job["id"]  # same company+title+location


def test_job_feed_search_filters_and_paging(client: TestClient) -> None:
    for i in range(5):
        client.post(
            "/api/v1/jobs", json=_job(title=f"Engineer {i}", url=f"https://example.com/j/{i}")
        )
    client.post(
        "/api/v1/jobs",
        json=_job(
            title="Data Analyst",
            url="https://example.com/d",
            work_mode="remote",
            description="Excel and dashboards for a remote analytics team, entry level.",
        ),
    )

    seen: list[int] = []
    cursor = None
    while True:
        params: dict[str, object] = {"limit": 4}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/api/v1/jobs", params=params).json()
        seen += [j["id"] for j in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 6
    assert seen == sorted(seen, reverse=True)  # newest first, no duplicates across pages

    hits = client.get("/api/v1/jobs", params={"q": "dashboards"}).json()["items"]
    assert [j["title"] for j in hits] == ["Data Analyst"]
    remote = client.get("/api/v1/jobs", params={"work_mode": "remote"}).json()["items"]
    assert len(remote) == 1


def test_extract_enqueues_one_task_per_job(client: TestClient) -> None:
    job = client.post("/api/v1/jobs", json=_job()).json()
    first = client.post(f"/api/v1/jobs/{job['id']}/extract")
    assert first.status_code == 202
    assert first.json()["created"] is True
    second = client.post(f"/api/v1/jobs/{job['id']}/extract").json()
    assert second["created"] is False
    assert second["task"]["id"] == first.json()["task"]["id"]
    assert client.post("/api/v1/jobs/999999/extract").status_code == 404
