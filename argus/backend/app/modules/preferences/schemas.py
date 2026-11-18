from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from app.shared.schemas import StrictModel

ExperienceLevel = Literal["fresher", "internship", "entry", "junior", "associate"]
WorkMode = Literal["remote", "hybrid", "onsite"]


class ScoringWeights(StrictModel):
    """Relative importance of each criterion in the fit score (normalized when scoring)."""

    title: float = Field(0.25, ge=0, le=1)
    required_skills: float = Field(0.30, ge=0, le=1)
    preferred_skills: float = Field(0.10, ge=0, le=1)
    experience: float = Field(0.20, ge=0, le=1)
    location: float = Field(0.10, ge=0, le=1)
    freshness: float = Field(0.05, ge=0, le=1)


class HardFilters(StrictModel):
    """A job failing any enabled hard filter is never auto-applied to, whatever its score."""

    max_required_years: float | None = Field(
        2, ge=0, le=30, description="Reject jobs requiring more years than this."
    )
    require_entry_level_friendly: bool = False
    enforce_work_modes: bool = True
    enforce_locations: bool = False
    enforce_excluded_companies: bool = True
    enforce_excluded_keywords: bool = True


class PreferencesFields(StrictModel):
    target_titles: list[str] = Field(
        default_factory=list, max_length=50, examples=[["Software Engineer", "Backend Developer"]]
    )
    experience_levels: list[ExperienceLevel] = Field(
        default_factory=list, examples=[["fresher", "entry", "junior"]]
    )
    min_years_experience: Decimal | None = Field(None, ge=0, le=50, max_digits=4, decimal_places=1)
    max_years_experience: Decimal | None = Field(None, ge=0, le=50, max_digits=4, decimal_places=1)
    locations: list[str] = Field(
        default_factory=list, max_length=50, examples=[["Bengaluru", "Chennai"]]
    )
    countries: list[str] = Field(default_factory=list, max_length=50, examples=[["India"]])
    work_modes: list[WorkMode] = Field(default_factory=list, examples=[["remote", "hybrid"]])
    employment_types: list[str] = Field(
        default_factory=list, max_length=10, examples=[["full_time", "internship"]]
    )
    excluded_companies: list[str] = Field(default_factory=list, max_length=500)
    excluded_keywords: list[str] = Field(
        default_factory=list, max_length=200, examples=[["senior", "staff", "principal"]]
    )
    willing_to_relocate: bool | None = None
    min_salary: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    salary_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    hard_filters: HardFilters = Field(default_factory=HardFilters)

    @model_validator(mode="after")
    def _years_range(self) -> Self:
        lo, hi = self.min_years_experience, self.max_years_experience
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("min_years_experience must be <= max_years_experience")
        return self


class PreferencesUpdate(PreferencesFields):
    """Full replacement (PUT)."""


class PreferencesOut(PreferencesFields):
    model_config = ConfigDict(extra="ignore")
    updated_at: datetime | None = Field(None, description="null = never saved (defaults shown).")
