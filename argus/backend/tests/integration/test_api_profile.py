"""Profile, skills (synonyms + bulk insert) and preferences."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

PROFILE = {
    "full_name": "Test Candidate",
    "email": "candidate@example.com",
    "phone": "+91 90000 00000",
    "location": "Chennai, India",
    "linkedin_url": "https://www.linkedin.com/in/test-candidate",
    "notice_period": "Immediate",
    "expected_salary_min": "450000.00",
    "expected_salary_currency": "INR",
}


def test_profile_starts_empty_then_round_trips(client: TestClient) -> None:
    empty = client.get("/api/v1/profile").json()
    assert empty["updated_at"] is None

    saved = client.put("/api/v1/profile", json=PROFILE)
    assert saved.status_code == 200
    body = client.get("/api/v1/profile").json()
    assert body["full_name"] == "Test Candidate"
    assert body["linkedin_url"] == "https://www.linkedin.com/in/test-candidate"
    assert body["expected_salary_min"] == "450000.00"


def test_profile_audit_never_contains_personal_values(client: TestClient) -> None:
    client.put("/api/v1/profile", json=PROFILE)
    event = client.get("/api/v1/audit-events", params={"action": "profile.updated"}).json()
    details = str(event["items"][0]["details"])
    assert "candidate@example.com" not in details
    assert "email" in details  # only field names are recorded


def test_profile_validation(client: TestClient) -> None:
    assert client.put("/api/v1/profile", json={"email": "not-an-email"}).status_code == 422
    assert client.put("/api/v1/profile", json={"unknown_field": 1}).status_code == 422
    assert (
        client.put("/api/v1/profile", json={"expected_salary_currency": "rupees"}).status_code
        == 422
    )


def test_skill_synonyms_and_conflicts(client: TestClient) -> None:
    js = client.post("/api/v1/profile/skills", json={"name": "JS", "proficiency": "intermediate"})
    assert js.status_code == 201
    assert js.json()["normalized_name"] == "javascript"

    dup = client.post("/api/v1/profile/skills", json={"name": "JavaScript"})
    assert dup.status_code == 409


def test_bulk_skills_skip_existing_and_in_batch_duplicates(client: TestClient) -> None:
    client.post("/api/v1/profile/skills", json={"name": "Python"})
    result = client.post(
        "/api/v1/profile/skills/bulk",
        json={
            "skills": [
                {"name": "py"},
                {"name": "Postgres"},
                {"name": "PostgreSQL"},
                {"name": "FastAPI", "verified": True},
            ]
        },
    ).json()
    assert sorted(s["normalized_name"] for s in result["created"]) == ["fastapi", "postgresql"]
    assert result["skipped"] == 2
    names = [s["normalized_name"] for s in client.get("/api/v1/profile/skills").json()]
    assert names == ["fastapi", "postgresql", "python"]


def test_skill_update_and_delete(client: TestClient) -> None:
    skill = client.post("/api/v1/profile/skills", json={"name": "k8s"}).json()
    assert skill["normalized_name"] == "kubernetes"
    updated = client.patch(f"/api/v1/profile/skills/{skill['id']}", json={"verified": True})
    assert updated.json()["verified"] is True
    assert client.delete(f"/api/v1/profile/skills/{skill['id']}").status_code == 204
    assert client.delete(f"/api/v1/profile/skills/{skill['id']}").status_code == 404


def test_preferences_defaults_and_validation(client: TestClient) -> None:
    defaults = client.get("/api/v1/preferences").json()
    assert defaults["updated_at"] is None
    assert defaults["hard_filters"]["max_required_years"] == 2

    prefs = {
        "target_titles": ["Software Engineer"],
        "experience_levels": ["fresher", "junior"],
        "work_modes": ["remote", "hybrid"],
        "locations": ["Chennai"],
        "scoring_weights": {"title": 0.4},
    }
    saved = client.put("/api/v1/preferences", json=prefs).json()
    assert saved["work_modes"] == ["remote", "hybrid"]
    assert saved["scoring_weights"]["title"] == 0.4
    assert saved["updated_at"] is not None

    bad = client.put(
        "/api/v1/preferences", json={"min_years_experience": 3, "max_years_experience": 1}
    )
    assert bad.status_code == 422
    assert client.put("/api/v1/preferences", json={"work_modes": ["moon"]}).status_code == 422
