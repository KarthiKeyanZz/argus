"""Explainable fit scoring - pure functions, no I/O.

A score is a *ranking aid*, not a probability of getting hired. Every component is
in [0, 1], combined with the user's weights, and each decision is recorded in the
breakdown so the UI can show exactly why a job ranked where it did. Hard filters
are reported separately and never hidden behind a high score.

Thresholds below were calibrated on nomic-embed-text (no prefix):
* skill pairs: unrelated pairs scored <= 0.614, true synonyms 0.75-0.98
  -> 0.70 counts as a match (zero false positives on the calibration set).
* job titles: an entry-level backend role vs "junior python backend developer"
  scored 0.69, "Restaurant Manager" 0.42 -> map [0.45, 0.75] onto [0, 1].
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.shared.text import company_key, normalize_text

SKILL_MATCH_THRESHOLD = 0.70
SKILL_RELATED_THRESHOLD = 0.60  # shown as "related" in the UI, earns no credit
TITLE_SIM_FLOOR, TITLE_SIM_CEIL = 0.45, 0.75
NEUTRAL = 0.5  # used when the posting doesn't say (unknown != bad)

SkillStatus = Literal["exact", "similar", "related", "missing"]


@dataclass(frozen=True, slots=True)
class SkillHit:
    skill: str
    exact: bool
    nearest: str | None
    similarity: float | None

    @property
    def status(self) -> SkillStatus:
        if self.exact:
            return "exact"
        if self.similarity is not None and self.similarity >= SKILL_MATCH_THRESHOLD:
            return "similar"
        if self.similarity is not None and self.similarity >= SKILL_RELATED_THRESHOLD:
            return "related"
        return "missing"

    @property
    def credit(self) -> float:
        status = self.status
        if status == "exact":
            return 1.0
        if status == "similar":
            return float(self.similarity or 0.0)
        return 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "status": self.status,
            "matched_with": self.nearest if self.status != "missing" else None,
            "similarity": round(self.similarity, 3) if self.similarity is not None else None,
        }


@dataclass(slots=True)
class JobInput:
    title: str
    company_name: str
    location_text: str | None
    work_mode: str  # job.work_mode, may be 'unknown'
    first_seen_at: datetime
    posted_at: datetime | None
    min_years: float | None
    max_years: float | None
    seniority: str | None
    entry_level_friendly: bool | None
    extracted_work_mode: str | None
    required: list[SkillHit] = field(default_factory=list)
    preferred: list[SkillHit] = field(default_factory=list)
    title_similarity: float | None = None


@dataclass(slots=True)
class Prefs:
    weights: dict[str, float]
    max_required_years: float | None
    require_entry_level_friendly: bool
    enforce_work_modes: bool
    enforce_locations: bool
    enforce_excluded_companies: bool
    enforce_excluded_keywords: bool
    work_modes: frozenset[str]
    locations: tuple[str, ...]
    excluded_company_keys: frozenset[str]
    excluded_keywords: tuple[str, ...]

    @classmethod
    def from_row(cls, row: dict[str, Any] | None) -> Prefs:
        row = row or {}
        hard = row.get("hard_filters") or {}
        weights = {
            "title": 0.25, "required_skills": 0.30, "preferred_skills": 0.10,
            "experience": 0.20, "location": 0.10, "freshness": 0.05,
            **(row.get("scoring_weights") or {}),
        }  # fmt: skip
        max_years = hard.get("max_required_years", 2)
        if row.get("max_years_experience") is not None and max_years is None:
            max_years = float(row["max_years_experience"])
        return cls(
            weights=weights,
            max_required_years=float(max_years) if max_years is not None else None,
            require_entry_level_friendly=bool(hard.get("require_entry_level_friendly", False)),
            enforce_work_modes=bool(hard.get("enforce_work_modes", True)),
            enforce_locations=bool(hard.get("enforce_locations", False)),
            enforce_excluded_companies=bool(hard.get("enforce_excluded_companies", True)),
            enforce_excluded_keywords=bool(hard.get("enforce_excluded_keywords", True)),
            work_modes=frozenset(row.get("work_modes") or ()),
            locations=tuple(normalize_text(x) for x in row.get("locations") or () if x),
            excluded_company_keys=frozenset(
                company_key(x) for x in row.get("excluded_companies") or () if x
            ),
            excluded_keywords=tuple(
                normalize_text(x) for x in row.get("excluded_keywords") or () if x
            ),
        )


@dataclass(slots=True)
class MatchResult:
    score: float
    passed_hard_filters: bool
    hard_fail_reasons: list[str]
    breakdown: dict[str, Any]


# ----------------------------------------------------------------------------- components


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def skill_coverage(hits: list[SkillHit]) -> float | None:
    if not hits:
        return None  # posting lists none -> unknown
    return sum(h.credit for h in hits) / len(hits)


def title_component(similarity: float | None) -> float | None:
    if similarity is None:
        return None
    return _clamp((similarity - TITLE_SIM_FLOOR) / (TITLE_SIM_CEIL - TITLE_SIM_FLOOR))


def experience_component(job: JobInput, max_years: float | None) -> tuple[float, str]:
    if job.min_years is not None:
        if max_years is None or job.min_years <= max_years:
            return 1.0, f"requires {job.min_years:g}+ years - within your range"
        return 0.0, f"requires {job.min_years:g}+ years - above your max of {max_years:g}"
    if job.entry_level_friendly:
        return 1.0, "explicitly open to freshers / new graduates"
    if job.seniority in {"senior", "lead"}:
        return 0.2, f"no years stated, but seniority is '{job.seniority}'"
    return 0.7, "no experience requirement stated"


def _work_mode(job: JobInput) -> str:
    if job.work_mode != "unknown":
        return job.work_mode
    return job.extracted_work_mode or "unknown"


def _location_matches(job: JobInput, prefs: Prefs) -> bool | None:
    if not prefs.locations:
        return None
    if _work_mode(job) == "remote":
        return True
    if not job.location_text:
        return None
    text = normalize_text(job.location_text)
    return any(loc in text for loc in prefs.locations)  # O(L) per job


def location_component(job: JobInput, prefs: Prefs) -> tuple[float, str]:
    mode = _work_mode(job)
    parts: list[float] = []
    notes: list[str] = []
    if prefs.work_modes:
        if mode == "unknown":
            parts.append(NEUTRAL)
            notes.append("work mode not stated")
        else:
            ok = mode in prefs.work_modes
            parts.append(1.0 if ok else 0.0)
            notes.append(f"{mode} {'matches' if ok else 'is not in'} your work modes")
    loc = _location_matches(job, prefs)
    if loc is not None:
        parts.append(1.0 if loc else 0.2)
        notes.append("location matches" if loc else "location not in your list")
    if not parts:
        return NEUTRAL, "no location preferences set"
    return sum(parts) / len(parts), "; ".join(notes)


def freshness_component(job: JobInput, now: datetime) -> float:
    seen = job.posted_at or job.first_seen_at
    age_days = max(0.0, (now - seen).total_seconds() / 86_400)
    if age_days <= 7:
        return 1.0
    return _clamp(1.0 - (age_days - 7) / 53 * 0.8)  # linear to 0.2 at 60 days


def hard_filter_reasons(job: JobInput, prefs: Prefs) -> list[str]:
    reasons: list[str] = []
    if (
        prefs.max_required_years is not None
        and job.min_years is not None
        and job.min_years > prefs.max_required_years
    ):
        reasons.append(
            f"requires {job.min_years:g}+ years (your max: {prefs.max_required_years:g})"
        )
    if prefs.require_entry_level_friendly and job.entry_level_friendly is False:
        reasons.append("not marked as open to freshers")
    mode = _work_mode(job)
    if (
        prefs.enforce_work_modes
        and prefs.work_modes
        and mode != "unknown"
        and mode not in prefs.work_modes
    ):
        reasons.append(f"work mode '{mode}' not in your preferences")
    if prefs.enforce_locations and _location_matches(job, prefs) is False:
        reasons.append("location not in your preferred locations")
    if (
        prefs.enforce_excluded_companies
        and company_key(job.company_name) in prefs.excluded_company_keys
    ):
        reasons.append("company is in your excluded list")
    if prefs.enforce_excluded_keywords and prefs.excluded_keywords:
        padded_title = f" {re.sub(r'[^a-z0-9+#.]+', ' ', normalize_text(job.title))} "
        hit = next((kw for kw in prefs.excluded_keywords if f" {kw} " in padded_title), None)
        if hit:
            reasons.append(f"title contains excluded keyword '{hit}'")
    return reasons


# ----------------------------------------------------------------------------- total


def score_job(job: JobInput, prefs: Prefs, now: datetime | None = None) -> MatchResult:
    now = now or datetime.now(UTC)
    experience, experience_note = experience_component(job, prefs.max_required_years)
    location, location_note = location_component(job, prefs)
    raw_components: dict[str, float | None] = {
        "title": title_component(job.title_similarity),
        "required_skills": skill_coverage(job.required),
        "preferred_skills": skill_coverage(job.preferred),
        "experience": experience,
        "location": location,
        "freshness": freshness_component(job, now),
    }
    # Unknown components count as neutral, so a posting is not punished for brevity.
    components = {k: (NEUTRAL if v is None else v) for k, v in raw_components.items()}
    weights = {k: max(0.0, float(prefs.weights.get(k, 0.0))) for k in components}
    total_weight = sum(weights.values()) or 1.0
    score = 100 * sum(components[k] * weights[k] for k in components) / total_weight

    reasons = hard_filter_reasons(job, prefs)
    breakdown = {
        "components": {k: round(v, 3) for k, v in components.items()},
        "unknown_components": sorted(k for k, v in raw_components.items() if v is None),
        "weights": {k: round(w / total_weight, 3) for k, w in weights.items()},
        "title_similarity": round(job.title_similarity, 3)
        if job.title_similarity is not None
        else None,
        "experience_note": experience_note,
        "location_note": location_note,
        "skills": {
            "required": [h.as_dict() for h in job.required],
            "preferred": [h.as_dict() for h in job.preferred],
            "threshold": SKILL_MATCH_THRESHOLD,
        },
    }
    return MatchResult(
        score=round(score, 2),
        passed_hard_filters=not reasons,
        hard_fail_reasons=reasons,
        breakdown=breakdown,
    )
