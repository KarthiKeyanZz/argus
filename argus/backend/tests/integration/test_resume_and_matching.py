"""Resume upload -> parse -> import, profile sections, export/delete, and matching.

Ollama is mocked. Fake embeddings are deterministic one-hot vectors per "concept":
texts in the same concept group get similarity ~0.92, everything else ~0.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.pool import Database
from app.modules.jobs import repository as jobs_repo
from app.modules.llm.client import OllamaClient
from app.modules.llm.service import LLMService
from app.modules.matching import service as matching
from tests.unit.test_scoring_and_resume_helpers import make_docx

pytestmark = pytest.mark.integration
OLLAMA = "http://ollama.test"
DIM = 768

CONCEPTS = {
    "algorithm design": "dsa", "data structures and algorithms": "dsa",
    "software engineer": "swe", "software engineer intern": "swe",
    "senior software engineer": "swe",
}  # fmt: skip


def _bucket(text: str, salt: str = "") -> int:
    return int(hashlib.sha256((salt + text).encode()).hexdigest(), 16) % (DIM - 1)


def fake_embed(request: httpx.Request) -> httpx.Response:
    texts = json.loads(request.content)["input"]
    vectors = []
    for text in texts:
        v = [0.0] * DIM
        v[_bucket(CONCEPTS.get(text, text))] = 1.0
        v[DIM - 1] = 0.3 if text in CONCEPTS else 0.0  # synonyms: ~0.92, not identical
        vectors.append(v)
    return httpx.Response(200, json={"embeddings": vectors})


RESUME_TEXT = """Alex Example
Chennai, India | alex.example@example.com
Backend Developer Intern, Example Labs (Jun 2025 - Aug 2025)
- Built REST APIs with FastAPI and PostgreSQL
Skills: Python, JS, Postgres, Docker"""

FACTS = {
    "full_name": "Alex Example", "email": "alex.example@example.com", "phone": None,
    "location": "Chennai, India", "headline": "Backend developer", "summary": None,
    "linkedin_url": None, "github_url": "https://github.com/alex-example", "portfolio_url": None,
    "education": [{"institution": "Example Institute", "degree": "B.E.",
                   "field_of_study": "Computer Science", "start_year": 2022, "end_year": 2026,
                   "grade": "8.4"}],
    "experience": [{"company": "Example Labs", "title": "Backend Developer Intern",
                    "employment_type": "internship", "location": "Chennai", "start": "Jun 2025",
                    "end": "Aug 2025",
                    "highlights": ["Built REST APIs with FastAPI and PostgreSQL"]}],
    "projects": [{"name": "Job Tracker", "description": None, "tech": ["React", "Node.js"],
                  "url": None}],
    "certifications": [],
    "skills": ["Python", "JS", "Postgres", "Docker"],
}  # fmt: skip


def _upload(client: TestClient, text: str = RESUME_TEXT) -> dict[str, Any]:
    data = make_docx(text)
    r = client.post(
        "/api/v1/resumes",
        files={"file": ("cv.docx", data, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    return r.json()


@respx.mock
def test_resume_upload_parse_import_flow(client: TestClient, settings: Settings) -> None:
    first = _upload(client)
    assert first["created"] is True
    assert first["resume"]["is_master"] is True
    assert _upload(client)["created"] is False  # same bytes -> deduplicated by SHA-256

    resume_id = first["resume"]["id"]
    assert "FastAPI" in client.get(f"/api/v1/resumes/{resume_id}").json()["extracted_text"]
    stored = list((settings.data_dir / "resumes").iterdir())
    assert len(stored) == 1

    chat = respx.post(f"{OLLAMA}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "fake",
                "done_reason": "stop",
                "message": {"content": json.dumps(FACTS)},
            },
        )
    )
    parsed = client.post(f"/api/v1/resumes/{resume_id}/parse").json()
    sent = json.loads(chat.calls.last.request.content)
    assert sent["think"] is False
    assert sent["options"]["num_predict"] == 4096
    assert "<<<RESUME" in sent["messages"][1]["content"]
    assert parsed["durations"][0]["months"] == 3  # computed in code
    assert parsed["facts"]["skills"] == ["python", "js", "postgres", "docker"]

    result = client.post(f"/api/v1/resumes/{resume_id}/import", json={"facts": parsed["facts"]})
    assert result.status_code == 200, result.text
    body = result.json()
    assert (body["education"], body["experience"], body["achievements"], body["projects"]) == (
        1,
        1,
        1,
        1,
    )
    profile = client.get("/api/v1/profile").json()
    assert profile["full_name"] == "Alex Example"
    experience = client.get("/api/v1/profile/experience").json()
    assert experience[0]["highlights"] == ["Built REST APIs with FastAPI and PostgreSQL"]
    assert experience[0]["start_date"] == "2025-06-01"
    assert experience[0]["source"] == "resume"
    skills = {s["normalized_name"] for s in client.get("/api/v1/profile/skills").json()}
    assert {"python", "javascript", "postgresql", "docker", "react", "node.js"} <= skills

    again = client.post(f"/api/v1/resumes/{resume_id}/import", json={"facts": parsed["facts"]})
    assert again.json()["skills_created"] == 0  # idempotent
    assert len(client.get("/api/v1/profile/experience").json()) == 1  # replaced, not duplicated


def test_resume_rejects_non_resume_files(client: TestClient) -> None:
    r = client.post(
        "/api/v1/resumes", files={"file": ("x.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")}
    )
    assert r.status_code == 422
    assert "PDF or DOCX" in r.json()["error"]["message"]


def test_profile_sections_crud(client: TestClient) -> None:
    created = client.post(
        "/api/v1/profile/education",
        json={"institution": "Example Institute", "degree": "B.E.", "start_date": "2022-07-01"},
    )
    assert created.status_code == 201
    row = created.json()
    updated = client.put(
        f"/api/v1/profile/education/{row['id']}",
        json={"institution": "Example Institute", "degree": "B.E.", "grade": "8.4"},
    )
    assert updated.json()["grade"] == "8.4"
    bad = client.put(
        f"/api/v1/profile/education/{row['id']}",
        json={"institution": "X", "start_date": "2026-01-01", "end_date": "2020-01-01"},
    )
    assert bad.status_code == 422  # CHECK constraint -> friendly error
    assert client.delete(f"/api/v1/profile/education/{row['id']}").status_code == 204
    assert client.delete(f"/api/v1/profile/education/{row['id']}").status_code == 404

    project = client.post("/api/v1/profile/projects", json={"name": "Bot", "tech": ["python"]})
    assert project.json()["tech"] == ["python"]


def test_export_and_delete_all_personal_data(client: TestClient, settings: Settings) -> None:
    _upload(client, RESUME_TEXT + "\nunique-for-delete-test")
    client.put("/api/v1/profile", json={"full_name": "Alex Example"})
    client.post("/api/v1/profile/skills", json={"name": "Python"})
    exported = client.get("/api/v1/profile/export").json()
    assert exported["profile"]["full_name"] == "Alex Example"
    assert len(exported["resumes"]) == 1
    assert {"education", "experience", "projects", "certifications"} <= exported.keys()

    assert client.delete("/api/v1/profile/data", params={"confirm": "yes"}).status_code == 422
    result = client.delete("/api/v1/profile/data", params={"confirm": "DELETE"}).json()
    assert result["files_removed"] == 1
    assert client.get("/api/v1/profile").json()["full_name"] is None
    assert client.get("/api/v1/profile/skills").json() == []
    assert not any((settings.data_dir / "resumes").iterdir())


# ----------------------------------------------------------------------------- matching


def _add_job(client: TestClient, db: Database, title: str, extraction: dict[str, Any]) -> int:
    url = "https://example.com/" + title.replace(" ", "-")
    job = client.post("/api/v1/jobs", json={
        "company_name": "Acme", "title": title, "url": url,
        "location": "Chennai", "work_mode": "onsite", "description": "Posting text " * 10,
    }).json()  # fmt: skip
    with db.transaction() as cur:
        jobs_repo.upsert_extraction(cur, {
            "job_id": job["id"], "method": "llm", "model": "fake", "extractor_version": 2,
            "min_years": None, "max_years": None, "education_level": "bachelor",
            "seniority": "entry", "employment_type": "internship", "work_mode": "onsite",
            "entry_level_friendly": True, "summary": "x", "education_fields": [],
            "raw": {}, "duration_ms": 1, "required_skills": [], "preferred_skills": [],
            **extraction,
        })  # fmt: skip
    return int(job["id"])


@respx.mock
def test_matching_semantic_skills_hard_filters_and_shortlist(
    client: TestClient, db: Database, settings: Settings
) -> None:
    respx.post(f"{OLLAMA}/api/embed").mock(side_effect=fake_embed)
    client.post(
        "/api/v1/profile/skills/bulk",
        json={
            "skills": [
                {"name": "Python"},
                {"name": "Data Structures and Algorithms"},
                {"name": "Docker"},
            ]
        },
    )
    client.put("/api/v1/preferences", json={
        "target_titles": ["Software Engineer"], "work_modes": ["onsite", "hybrid"],
        "excluded_keywords": ["senior"]})  # fmt: skip

    good = _add_job(
        client,
        db,
        "Software Engineer Intern",
        {"required_skills": ["python", "algorithm design", "go"], "preferred_skills": ["docker"]},
    )
    senior = _add_job(client, db, "Senior Software Engineer", {
        "required_skills": ["python"], "min_years": 6, "seniority": "senior",
        "entry_level_friendly": False})  # fmt: skip

    llm = LLMService(OllamaClient(OLLAMA, timeout_s=5), settings)
    result = matching.score_jobs(db, llm)
    assert result == {"scored": 2, "passed_hard_filters": 1}

    detail = client.get(f"/api/v1/jobs/{good}").json()
    match = detail["match"]
    statuses = {s["skill"]: s["status"] for s in match["breakdown"]["skills"]["required"]}
    assert statuses == {"python": "exact", "algorithm design": "similar", "go": "missing"}
    assert match["passed_hard_filters"] is True
    assert match["breakdown"]["title_similarity"] > 0.9

    bad = client.get(f"/api/v1/jobs/{senior}").json()["match"]
    assert bad["passed_hard_filters"] is False
    assert any("6+ years" in r for r in bad["hard_fail_reasons"])
    assert any("senior" in r for r in bad["hard_fail_reasons"])

    shortlist = client.get("/api/v1/matching/shortlist").json()["items"]
    assert [j["id"] for j in shortlist] == [good]
    everything = client.get("/api/v1/matching/shortlist", params={"include_failed": True}).json()
    assert [j["id"] for j in everything["items"]] == [good, senior]

    # every distinct text is embedded once; a second run re-uses the cache
    calls_before = respx.calls.call_count
    matching.score_jobs(db, llm)
    assert respx.calls.call_count == calls_before
    llm.client.close()


def test_matching_run_endpoint_enqueues_once(client: TestClient) -> None:
    first = client.post("/api/v1/matching/run").json()
    second = client.post("/api/v1/matching/run").json()
    assert first["created"] is True
    assert second["created"] is False
