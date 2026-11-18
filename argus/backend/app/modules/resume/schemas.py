"""Resume schemas. `ResumeFacts` doubles as the LLM output schema (constrained decoding).

Lessons applied from testing:
* Never ask the model to compute (e.g. months of experience) - it copies dates,
  code does the arithmetic.
* Dates have a regex `pattern`, so the grammar only allows 'Jun 2025', '2025' or
  'Present' - the model cannot append commentary like "(implied by context...)".
* Every list has `maxItems`, so a repetition loop is cut off by the grammar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.llm.schemas import GenerationMetrics
from app.shared.schemas import StrictModel

MONTH_YEAR = r"^((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) )?[12][0-9]{3}$"
MONTH_YEAR_OR_PRESENT = (
    r"^(((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) )?[12][0-9]{3}|Present)$"
)

EmploymentType = Literal["full_time", "part_time", "internship", "contract", "freelance"]


class FactEducation(BaseModel):
    institution: str = Field(max_length=200)
    degree: str = Field(max_length=200, description="As written, e.g. 'B.E.' or 'B.Tech'")
    field_of_study: str | None = Field(None, max_length=200)
    start_year: int | None = Field(None, ge=1950, le=2100)
    end_year: int | None = Field(None, ge=1950, le=2100)
    grade: str | None = Field(None, max_length=50, description="CGPA / percentage as written")


class FactExperience(BaseModel):
    company: str = Field(max_length=200)
    title: str = Field(max_length=200)
    employment_type: EmploymentType
    location: str | None = Field(None, max_length=200)
    start: str | None = Field(None, pattern=MONTH_YEAR, description="'Jun 2025' or '2025'")
    end: str | None = Field(
        None, pattern=MONTH_YEAR_OR_PRESENT, description="'Aug 2025', '2025' or 'Present'"
    )
    highlights: list[str] = Field(
        default_factory=list, max_length=8, description="Bullet points, copied as written"
    )


class FactProject(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = Field(None, max_length=1000)
    tech: list[str] = Field(default_factory=list, max_length=15)
    url: str | None = Field(None, max_length=300)


class FactCertification(BaseModel):
    name: str = Field(max_length=200)
    issuer: str | None = Field(None, max_length=200)


class ResumeFacts(BaseModel):
    full_name: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=40)
    location: str | None = Field(None, max_length=200)
    headline: str | None = Field(None, max_length=300, description="One-line headline")
    summary: str | None = Field(None, max_length=2000)
    linkedin_url: str | None = Field(None, max_length=300)
    github_url: str | None = Field(None, max_length=300)
    portfolio_url: str | None = Field(None, max_length=300)
    education: list[FactEducation] = Field(default_factory=list, max_length=6)
    experience: list[FactExperience] = Field(default_factory=list, max_length=12)
    projects: list[FactProject] = Field(default_factory=list, max_length=12)
    certifications: list[FactCertification] = Field(default_factory=list, max_length=12)
    skills: list[str] = Field(default_factory=list, max_length=60)


class ExperienceDuration(BaseModel):
    company: str
    title: str
    months: int | None = Field(description="Computed in code from start/end, inclusive.")


class ResumeOut(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    is_master: bool
    uploaded_at: datetime
    text_chars: int


class ResumeDetail(ResumeOut):
    extracted_text: str


class ResumeUploadResult(BaseModel):
    resume: ResumeOut
    created: bool = Field(description="False if this exact file was uploaded before.")


class ResumeParseResponse(BaseModel):
    resume_id: int
    model: str
    prompt_version: int
    facts: ResumeFacts
    durations: list[ExperienceDuration]
    total_experience_months: int = Field(description="Sum over roles (computed in code).")
    metrics: GenerationMetrics


class ResumeImportRequest(StrictModel):
    facts: ResumeFacts = Field(description="The reviewed (possibly edited) parse result.")
    replace_existing: bool = Field(
        True, description="Replace entries previously imported from a resume."
    )
    mark_verified: bool = Field(True, description="You reviewed these facts in the UI.")


class ResumeImportResult(BaseModel):
    profile_fields_updated: list[str]
    education: int
    experience: int
    achievements: int
    projects: int
    certifications: int
    skills_created: int
    skills_skipped: int
