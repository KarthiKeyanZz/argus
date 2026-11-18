"""Resume use-cases: upload -> parse (LLM, nothing saved) -> user reviews -> import."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import NotFoundError, UpstreamError
from app.db.pool import Database
from app.modules.audit import repository as audit
from app.modules.llm import prompts
from app.modules.llm.service import LLMService, metrics_from
from app.modules.llm.structured import llm_schema
from app.modules.profile import repository as profile_repo
from app.modules.resume import files
from app.modules.resume import repository as repo
from app.modules.resume.dates import months_between, parse_month_year
from app.modules.resume.schemas import (
    ExperienceDuration,
    ResumeDetail,
    ResumeFacts,
    ResumeImportRequest,
    ResumeImportResult,
    ResumeOut,
    ResumeParseResponse,
    ResumeUploadResult,
)
from app.shared.text import normalize_skill, unique_preserving_order

RESUME_MAX_TOKENS = 4096
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PROFILE_FIELDS = (
    "full_name", "email", "phone", "location", "headline", "summary",
    "linkedin_url", "github_url", "portfolio_url",
)  # fmt: skip


def with_scheme(url: str | None) -> str | None:
    """'linkedin.com/in/x' -> 'https://linkedin.com/in/x'; leaves full URLs alone."""
    if not url:
        return None
    url = url.strip()
    if "://" in url:
        return url if url.lower().startswith(("http://", "https://")) else None
    return f"https://{url}" if "." in url.split("/", 1)[0] else None


# ----------------------------------------------------------------------------- files


def upload(db: Database, data_dir: Path, filename: str, data: bytes) -> ResumeUploadResult:
    parsed = files.parse_upload(data)  # validates type/size and extracts text
    digest = hashlib.sha256(data).hexdigest()
    with db.transaction() as cur:
        existing = repo.find_by_sha(cur, digest)
    if existing:
        return ResumeUploadResult(resume=ResumeOut.model_validate(existing), created=False)

    stored_name = files.store(data_dir, parsed.kind, data)
    try:
        with db.transaction() as cur:
            row = repo.insert(
                cur,
                {
                    "original_filename": Path(filename or "resume").name[:200],
                    "stored_name": stored_name,
                    "mime_type": parsed.mime_type,
                    "size_bytes": len(data),
                    "sha256": digest,
                    "extracted_text": parsed.text,
                },
            )
            audit.record(
                cur,
                actor="user",
                action="resume.uploaded",
                entity_type="resume",
                entity_id=row["id"],
                details={"bytes": len(data), "type": parsed.kind},
            )
    except Exception:
        files.remove(data_dir, stored_name)  # don't leave orphan files behind
        raise
    return ResumeUploadResult(resume=ResumeOut.model_validate(row), created=True)


def list_resumes(db: Database) -> list[ResumeOut]:
    with db.transaction() as cur:
        return [ResumeOut.model_validate(r) for r in repo.list_all(cur)]


def get(db: Database, resume_id: int) -> ResumeDetail:
    with db.transaction() as cur:
        row = repo.get(cur, resume_id)
    if row is None:
        raise NotFoundError(f"Resume {resume_id} not found.")
    return ResumeDetail.model_validate(row)


def delete(db: Database, data_dir: Path, resume_id: int) -> None:
    with db.transaction() as cur:
        stored_name = repo.delete(cur, resume_id)
        if stored_name is None:
            raise NotFoundError(f"Resume {resume_id} not found.")
        audit.record(
            cur, actor="user", action="resume.deleted", entity_type="resume", entity_id=resume_id
        )
    files.remove(data_dir, stored_name)


# ----------------------------------------------------------------------------- parse


def parse(db: Database, llm: LLMService, resume_id: int) -> ResumeParseResponse:
    resume = get(db, resume_id)  # short transaction; no connection held during the LLM call
    body: dict[str, Any] = {
        "model": llm.settings.llm_chat_model,
        "messages": [
            {"role": "system", "content": prompts.RESUME_SYSTEM},
            {
                "role": "user",
                "content": prompts.RESUME_USER.format(
                    resume=prompts.fence_resume(
                        resume.extracted_text[: llm.settings.llm_max_input_chars]
                    )
                ),
            },
        ],
        "format": llm_schema(ResumeFacts),
        "think": False,
        "keep_alive": llm.settings.llm_keep_alive,
        "options": {
            "temperature": 0,
            "seed": 7,
            "num_ctx": llm.settings.llm_default_num_ctx,
            "num_predict": RESUME_MAX_TOKENS,
        },
    }
    data = llm.client.chat(body)
    content = (data.get("message") or {}).get("content", "")
    if data.get("done_reason") == "length":
        raise UpstreamError(
            "The model hit the output limit while reading the resume.",
            details={"raw_tail": content[-500:]},
        )
    try:
        facts = ResumeFacts.model_validate_json(content)
    except ValidationError as exc:
        raise UpstreamError(
            "The model's output did not match the resume schema.", details={"raw": content[:2000]}
        ) from exc

    facts.skills = unique_preserving_order(map(normalize_skill, facts.skills))
    # Resumes often omit the scheme ("linkedin.com/in/x"); forms and validators need it.
    facts.linkedin_url = with_scheme(facts.linkedin_url)
    facts.github_url = with_scheme(facts.github_url)
    facts.portfolio_url = with_scheme(facts.portfolio_url)
    for project in facts.projects:
        project.url = with_scheme(project.url)
    if facts.email and not _EMAIL.match(facts.email):
        facts.email = None

    durations: list[ExperienceDuration] = []
    for exp in facts.experience:  # arithmetic in code, never in the model
        months = months_between(parse_month_year(exp.start), parse_month_year(exp.end))
        durations.append(ExperienceDuration(company=exp.company, title=exp.title, months=months))
    return ResumeParseResponse(
        resume_id=resume_id,
        model=data.get("model", body["model"]),
        prompt_version=prompts.RESUME_EXTRACTION_VERSION,
        facts=facts,
        durations=durations,
        total_experience_months=sum(d.months or 0 for d in durations),
        metrics=metrics_from(data),
    )


# ----------------------------------------------------------------------------- import


def import_facts(db: Database, resume_id: int, req: ResumeImportRequest) -> ResumeImportResult:
    facts = req.facts
    ref = f"resume:{resume_id}"
    verified = req.mark_verified
    with db.transaction() as cur:
        if repo.get(cur, resume_id) is None:
            raise NotFoundError(f"Resume {resume_id} not found.")

        # Profile: fill in / overwrite only fields the resume actually provides.
        current = profile_repo.get_profile(cur) or {}
        merged = {k: current.get(k) for k in profile_repo.PROFILE_COLUMNS}
        updated = [f for f in _PROFILE_FIELDS if getattr(facts, f)]
        for field in updated:
            merged[field] = getattr(facts, field)
        profile_repo.upsert_profile(cur, merged)

        if req.replace_existing:
            repo.delete_imported(cur)

        education = repo.insert_education(
            cur,
            [
                (
                    e.institution,
                    e.degree,
                    e.field_of_study,
                    parse_month_year(str(e.start_year)) if e.start_year else None,
                    parse_month_year(str(e.end_year)) if e.end_year else None,
                    e.grade,
                    "resume",
                    ref,
                    verified,
                    i,
                )
                for i, e in enumerate(facts.education)
            ],
        )
        ids = repo.insert_experience(
            cur,
            [
                (
                    x.company,
                    x.title,
                    x.employment_type,
                    x.location,
                    parse_month_year(x.start),
                    None if (x.end or "").lower() == "present" else parse_month_year(x.end),
                    (x.end or "").lower() == "present",
                    "resume",
                    ref,
                    verified,
                    i,
                )
                for i, x in enumerate(facts.experience)
            ],
        )
        achievements = repo.insert_achievements(
            cur,
            [
                (ids[i], text, "resume", ref, verified, j)
                for i, x in enumerate(facts.experience)
                for j, text in enumerate(x.highlights)
            ],
        )
        projects = repo.insert_projects(
            cur,
            [
                (
                    p.name,
                    p.description,
                    p.url,
                    unique_preserving_order(map(normalize_skill, p.tech)),
                    "resume",
                    ref,
                    verified,
                    i,
                )
                for i, p in enumerate(facts.projects)
            ],
        )
        certifications = repo.insert_certifications(
            cur, [(c.name, c.issuer, "resume", ref, verified) for c in facts.certifications]
        )

        # Skills: listed skills + project technologies, de-duplicated in O(n).
        names = unique_preserving_order(
            [*facts.skills, *(normalize_skill(t) for p in facts.projects for t in p.tech)]
        )
        created = profile_repo.bulk_insert_skills(
            cur,
            [
                (name, normalize_skill(name), None, None, None, "resume", ref, verified)
                for name in names
            ],
        )
        audit.record(
            cur,
            actor="user",
            action="resume.imported",
            entity_type="resume",
            entity_id=resume_id,
            details={"fields": updated, "skills": len(created)},
        )
    return ResumeImportResult(
        profile_fields_updated=updated,
        education=education,
        experience=len(ids),
        achievements=achievements,
        projects=projects,
        certifications=certifications,
        skills_created=len(created),
        skills_skipped=len(names) - len(created),
    )
