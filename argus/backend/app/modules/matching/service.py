"""Matching use-cases: keep embeddings fresh, score jobs, read the shortlist.

Cost model for scoring N jobs with S distinct skills and P profile skills:
* embeddings: each distinct text is embedded once, ever (cache), in batches;
* per job: one indexed nearest-neighbour lookup per skill -> O(N * k * log P);
* no pairwise loops over jobs or skills.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from app.db.pool import Cursor, Database
from app.db.sql import Row
from app.modules.llm.service import LLMService
from app.modules.matching import repository as repo
from app.modules.matching.schemas import ShortlistItem
from app.modules.matching.scoring import JobInput, Prefs, SkillHit, score_job
from app.shared.pagination import Page, decode_cursor, paginate
from app.shared.text import normalize_text, unique_preserving_order

logger = logging.getLogger(__name__)

EMBED_BATCH = 128
SCORE_BATCH = 100


def ensure_embeddings(db: Database, llm: LLMService, texts: Iterable[str]) -> int:
    """Embed every text not cached yet. Returns how many were newly embedded."""
    wanted = unique_preserving_order(texts)
    if not wanted:
        return 0
    model = llm.settings.llm_embed_model
    with db.transaction() as cur:
        have = repo.cached_texts(cur, wanted, model)
    missing = [t for t in wanted if t not in have]  # set lookup: O(n)
    for start in range(0, len(missing), EMBED_BATCH):
        chunk = missing[start : start + EMBED_BATCH]
        vectors = llm.client.embed(model, chunk, keep_alive=llm.settings.llm_keep_alive)
        # LLM call happens with no DB connection held; write in a short transaction.
        with db.transaction() as cur:
            repo.store_embeddings(cur, model, list(zip(chunk, vectors, strict=True)))
    return len(missing)


def refresh_profile_vectors(db: Database, llm: LLMService) -> int:
    with db.transaction() as cur:
        names = repo.profile_skill_names_missing_vectors(cur)
    if not names:
        return 0
    ensure_embeddings(db, llm, names)
    with db.transaction() as cur:
        return repo.attach_profile_skill_vectors(cur)


def score_jobs(db: Database, llm: LLMService, job_ids: list[int] | None = None) -> dict[str, int]:
    """Score the given jobs (or every active, extracted job) in keyset batches."""
    refresh_profile_vectors(db, llm)
    with db.transaction() as cur:
        prefs_row = repo.get_preferences_row(cur)
    prefs = Prefs.from_row(prefs_row)
    targets = unique_preserving_order(
        normalize_text(t) for t in (prefs_row or {}).get("target_titles") or []
    )
    now = datetime.now(UTC)

    scored = passed = 0
    after_id: int | None = None
    while True:
        with db.transaction() as cur:
            batch = repo.jobs_to_score(cur, job_ids=job_ids, after_id=after_id, limit=SCORE_BATCH)
        if not batch:
            break
        after_id = int(batch[-1]["id"])

        # One embedding pass for the whole batch: all skills + titles + targets.
        texts: list[str] = [*targets]
        for row in batch:
            texts.append(row["title_normalized"])
            texts.extend(row["required_skills"])
            texts.extend(row["preferred_skills"])
        ensure_embeddings(db, llm, texts)

        with db.transaction() as cur:
            for row in batch:
                result = score_job(_job_input(cur, row, targets), prefs, now)
                repo.upsert_match(cur, int(row["id"]), result)
                repo.set_title_vector(cur, int(row["id"]), row["title_normalized"])
                scored += 1
                passed += int(result.passed_hard_filters)
        if len(batch) < SCORE_BATCH:
            break
    logger.info("scored %d job(s), %d passed hard filters", scored, passed)
    return {"scored": scored, "passed_hard_filters": passed}


def _job_input(cur: Cursor, row: Row, targets: list[str]) -> JobInput:
    required: list[str] = row["required_skills"]
    preferred: list[str] = row["preferred_skills"]
    hits = {
        h["skill"]: SkillHit(
            skill=h["skill"],
            exact=bool(h["exact"]),
            nearest=h["nearest"],
            similarity=float(h["similarity"]) if h["similarity"] is not None else None,
        )
        for h in repo.skill_hits(cur, unique_preserving_order([*required, *preferred]))
    }
    return JobInput(
        title=row["title"],
        company_name=row["company_name"],
        location_text=row["location_text"],
        work_mode=row["work_mode"],
        first_seen_at=row["first_seen_at"],
        posted_at=row["posted_at"],
        min_years=_float(row["min_years_experience"]),
        max_years=_float(row["max_years_experience"]),
        seniority=row["seniority"],
        entry_level_friendly=row["entry_level_friendly"],
        extracted_work_mode=row["extracted_work_mode"],
        required=[hits[s] for s in required if s in hits],
        preferred=[hits[s] for s in preferred if s in hits],
        title_similarity=repo.best_title_similarity(cur, row["title_normalized"], targets),
    )


def _float(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


def shortlist_page(
    db: Database, *, include_failed: bool, limit: int, cursor: str | None
) -> Page[ShortlistItem]:
    after = None
    if cursor:
        score, job_id = decode_cursor(cursor, 2)
        after = (str(score), int(job_id))
    with db.transaction() as cur:
        rows = repo.shortlist(cur, include_failed=include_failed, after=after, limit=limit)
    page, next_cursor = paginate(rows, limit, key=lambda r: (str(r["score"]), r["id"]))
    return Page(items=[ShortlistItem.model_validate(r) for r in page], next_cursor=next_cursor)
