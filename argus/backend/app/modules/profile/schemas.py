from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl

from app.shared.schemas import StrictModel

FactSource = Literal["user", "resume", "llm"]
Proficiency = Literal["beginner", "intermediate", "advanced", "expert"]


# ----------------------------------------------------------------------------- profile


class ProfileFields(StrictModel):
    full_name: str | None = Field(None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40, pattern=r"^[0-9+()\-.\s]{6,40}$")
    location: str | None = Field(None, max_length=200)
    headline: str | None = Field(None, max_length=300)
    summary: str | None = Field(None, max_length=5000)
    linkedin_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    portfolio_url: HttpUrl | None = None
    website_url: HttpUrl | None = None
    work_authorization: str | None = Field(
        None, max_length=300, description="Only if you choose to provide it."
    )
    requires_sponsorship: bool | None = None
    notice_period: str | None = Field(None, max_length=100, examples=["Immediate", "30 days"])
    available_from: date | None = None
    expected_salary_min: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    expected_salary_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$", examples=["INR"])


class ProfileUpdate(ProfileFields):
    """Full replacement of the profile (PUT semantics)."""


class ProfileOut(BaseModel):
    """Stored values (already validated on the way in)."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    website_url: str | None = None
    work_authorization: str | None = None
    requires_sponsorship: bool | None = None
    notice_period: str | None = None
    available_from: date | None = None
    expected_salary_min: Decimal | None = None
    expected_salary_currency: str | None = None
    updated_at: datetime | None = Field(None, description="null = profile not created yet.")


# ----------------------------------------------------------------------------- skills


class SkillBase(StrictModel):
    category: str | None = Field(None, max_length=100, examples=["language", "framework"])
    proficiency: Proficiency | None = None
    years_experience: Decimal | None = Field(None, ge=0, le=60, max_digits=4, decimal_places=1)
    source: FactSource = "user"
    source_ref: str | None = Field(None, max_length=300)
    verified: bool = False


class SkillCreate(SkillBase):
    name: str = Field(min_length=1, max_length=100, examples=["Python"])


class SkillUpdate(StrictModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    category: str | None = Field(None, max_length=100)
    proficiency: Proficiency | None = None
    years_experience: Decimal | None = Field(None, ge=0, le=60, max_digits=4, decimal_places=1)
    source_ref: str | None = Field(None, max_length=300)
    verified: bool | None = None


class SkillBulkCreate(StrictModel):
    skills: list[SkillCreate] = Field(min_length=1, max_length=500)


class SkillOut(BaseModel):
    id: int
    name: str
    normalized_name: str = Field(
        description="Canonical key after synonym mapping (js -> javascript)."
    )
    category: str | None
    proficiency: Proficiency | None
    years_experience: Decimal | None
    source: FactSource
    source_ref: str | None
    verified: bool
    created_at: datetime
    updated_at: datetime


class SkillBulkResult(BaseModel):
    created: list[SkillOut]
    skipped: int = Field(description="Skills that already existed (after synonym mapping).")


# ----------------------------------------------------------------------------- sections


class _SectionMeta(StrictModel):
    source: FactSource = "user"
    source_ref: str | None = Field(None, max_length=300)
    verified: bool = True


class _SectionOutMeta(BaseModel):
    id: int
    source: FactSource
    source_ref: str | None
    verified: bool
    created_at: datetime
    updated_at: datetime


class EducationIn(_SectionMeta):
    institution: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(None, max_length=200)
    field_of_study: str | None = Field(None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    grade: str | None = Field(None, max_length=50)
    sort_order: int = 0


class EducationOut(_SectionOutMeta):
    institution: str
    degree: str | None
    field_of_study: str | None
    start_date: date | None
    end_date: date | None
    grade: str | None
    sort_order: int


class ExperienceIn(_SectionMeta):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    employment_type: (
        Literal["full_time", "part_time", "internship", "contract", "freelance", "apprenticeship"]
        | None
    ) = None
    location: str | None = Field(None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str | None = Field(None, max_length=5000)
    sort_order: int = 0


class ExperienceOut(_SectionOutMeta):
    company: str
    title: str
    employment_type: str | None
    location: str | None
    start_date: date | None
    end_date: date | None
    is_current: bool
    description: str | None
    sort_order: int
    highlights: list[str] = Field(description="Verified bullet points for this role.")


class ProjectIn(_SectionMeta):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    url: str | None = Field(None, max_length=300)
    tech: list[str] = Field(default_factory=list, max_length=30)
    start_date: date | None = None
    end_date: date | None = None
    sort_order: int = 0


class ProjectOut(_SectionOutMeta):
    name: str
    description: str | None
    url: str | None
    tech: list[str]
    start_date: date | None
    end_date: date | None
    sort_order: int


class CertificationIn(_SectionMeta):
    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(None, max_length=200)
    issued_on: date | None = None
    expires_on: date | None = None
    credential_url: str | None = Field(None, max_length=300)


class CertificationOut(_SectionOutMeta):
    name: str
    issuer: str | None
    issued_on: date | None
    expires_on: date | None
    credential_url: str | None


class DataDeletionResult(BaseModel):
    deleted: dict[str, int]
    files_removed: int
