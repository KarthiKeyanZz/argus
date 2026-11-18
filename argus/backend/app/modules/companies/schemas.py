from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.companies.ats import AtsKind
from app.shared.schemas import StrictModel


class CompanyCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200, examples=["Stripe"])
    careers_url: HttpUrl | None = Field(
        None,
        description="Paste the careers page. Greenhouse / Lever / Ashby / SmartRecruiters "
        "boards are detected automatically.",
        examples=["https://job-boards.greenhouse.io/stripe"],
    )
    website_url: HttpUrl | None = None
    ats_kind: AtsKind | None = Field(None, description="Override auto-detection.")
    ats_token: str | None = Field(None, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._-]+$")
    enabled: bool = True
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _ats_pair(self) -> Self:
        if (self.ats_kind is None) != (self.ats_token is None):
            raise ValueError("ats_kind and ats_token must be given together")
        return self


class CompanyUpdate(StrictModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    careers_url: HttpUrl | None = None
    website_url: HttpUrl | None = None
    enabled: bool | None = None
    notes: str | None = Field(None, max_length=2000)


class CompanyOut(BaseModel):
    id: int
    name: str
    normalized_key: str
    website_url: str | None
    careers_url: str | None
    ats_kind: AtsKind | None
    ats_token: str | None
    enabled: bool
    notes: str | None
    last_discovered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AtsDetectRequest(StrictModel):
    url: HttpUrl = Field(examples=["https://jobs.lever.co/palantir"])


class AtsDetectResponse(BaseModel):
    detected: bool
    ats_kind: AtsKind | None = None
    ats_token: str | None = None
