from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from app.shared.schemas import StrictModel

JobStatus = Literal["active", "closed", "expired", "uncertain"]
WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]


class ManualJobCreate(StrictModel):
    """Add a job by hand - e.g. one you found on a portal that forbids automation."""

    company_name: str = Field(min_length=1, max_length=200, examples=["Acme Analytics"])
    title: str = Field(min_length=1, max_length=300, examples=["Junior Backend Engineer"])
    url: HttpUrl = Field(
        description="Link to the original posting.",
        examples=["https://example.com/careers/junior-backend-engineer"],
    )
    apply_url: HttpUrl | None = None
    location: str | None = Field(None, max_length=300, examples=["Bengaluru, India"])
    work_mode: WorkMode = "unknown"
    employment_type: str | None = Field(None, max_length=50, examples=["full_time"])
    description: str = Field(min_length=1, max_length=100_000)
    posted_at: datetime | None = None
    deadline_at: datetime | None = None


class JobSummary(BaseModel):
    """List view - no description, to keep pages small."""

    id: int
    title: str
    company_id: int
    company_name: str
    source: str
    location_text: str | None
    work_mode: WorkMode
    employment_type: str | None
    status: JobStatus
    posted_at: datetime | None
    deadline_at: datetime | None
    first_seen_at: datetime
    score: Decimal | None = Field(description="Fit score 0-100 once matching has run.")
    passed_hard_filters: bool | None


class JobExtractionOut(BaseModel):
    method: Literal["rules", "llm"]
    model: str | None
    extractor_version: int
    required_skills: list[str]
    preferred_skills: list[str]
    min_years_experience: Decimal | None
    max_years_experience: Decimal | None
    education_level: str | None
    seniority: str | None
    employment_type: str | None
    work_mode: str | None
    entry_level_friendly: bool | None
    summary: str | None
    education_fields: list[str] = []
    duration_ms: int | None
    extracted_at: datetime


class MatchOut(BaseModel):
    score: Decimal
    passed_hard_filters: bool
    hard_fail_reasons: list[str]
    breakdown: dict[str, Any] = Field(
        description="components, weights, per-skill status (exact/similar/related/missing), notes"
    )
    computed_at: datetime


class JobDetail(JobSummary):
    source_job_id: str
    canonical_url: str
    apply_url: str | None
    department: str | None
    description_text: str
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    salary_period: str | None
    last_seen_at: datetime
    closed_at: datetime | None
    duplicate_of: int | None
    extraction: JobExtractionOut | None
    match: MatchOut | None = None
