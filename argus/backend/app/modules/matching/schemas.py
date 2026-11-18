from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.modules.jobs.schemas import JobSummary


class ShortlistItem(JobSummary):
    score: Decimal = Field(description="Fit score 0-100 (ranking aid, not a hiring probability).")
    passed_hard_filters: bool
    hard_fail_reasons: list[str]
