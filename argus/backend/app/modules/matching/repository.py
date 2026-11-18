"""SQL for matching. Embeddings live in pgvector columns; similarity is computed in
the database with the cosine-distance operator ``<=>`` (similarity = 1 - distance)."""

from __future__ import annotations

from collections.abc import Sequence

from psycopg2.extras import Json, execute_values

from app.db.pool import Cursor
from app.db.sql import Row, fetch_all, fetch_one
from app.modules.matching.scoring import MatchResult


def to_vector_literal(vector: Sequence[float]) -> str:
    """pgvector text format: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"


# ----------------------------------------------------------------------------- embedding cache
# `skill_embedding` is a text -> vector cache keyed by normalized text. It stores
# skills, job titles and target titles alike: same text, same vector.


def cached_texts(cur: Cursor, texts: list[str], model: str) -> set[str]:
    cur.execute(
        "SELECT normalized_name FROM skill_embedding "
        "WHERE normalized_name = ANY(%s::text[]) AND model = %s",
        (texts, model),
    )
    return {r["normalized_name"] for r in cur.fetchall()}


def store_embeddings(cur: Cursor, model: str, items: list[tuple[str, list[float]]]) -> None:
    execute_values(
        cur,
        "INSERT INTO skill_embedding (normalized_name, model, embedding) VALUES %s "
        "ON CONFLICT (normalized_name) DO UPDATE "
        "SET model = EXCLUDED.model, embedding = EXCLUDED.embedding, created_at = now()",
        [(text, model, to_vector_literal(vec)) for text, vec in items],
        template="(%s, %s, %s::vector)",
        page_size=200,
    )


def profile_skill_names_missing_vectors(cur: Cursor) -> list[str]:
    cur.execute("SELECT normalized_name FROM skill WHERE embedding IS NULL")
    return [r["normalized_name"] for r in cur.fetchall()]


def attach_profile_skill_vectors(cur: Cursor) -> int:
    """Copy cached vectors onto profile skills (one set-based UPDATE)."""
    cur.execute(
        "UPDATE skill s SET embedding = e.embedding FROM skill_embedding e "
        "WHERE e.normalized_name = s.normalized_name AND s.embedding IS NULL"
    )
    return int(cur.rowcount)


# ----------------------------------------------------------------------------- jobs to score

_JOBS_TO_SCORE = """
SELECT j.id, j.title, j.title_normalized, j.location_text, j.work_mode, j.first_seen_at,
       j.posted_at, c.name AS company_name,
       e.min_years_experience, e.max_years_experience, e.seniority, e.entry_level_friendly,
       e.work_mode AS extracted_work_mode, e.required_skills, e.preferred_skills
FROM job j
JOIN company c ON c.id = j.company_id
JOIN job_extraction e ON e.job_id = j.id
WHERE j.status = 'active'
  AND (%(job_ids)s::bigint[] IS NULL OR j.id = ANY(%(job_ids)s::bigint[]))
  AND (%(after_id)s::bigint IS NULL OR j.id > %(after_id)s)
ORDER BY j.id
LIMIT %(limit)s
"""


def jobs_to_score(
    cur: Cursor, *, job_ids: list[int] | None, after_id: int | None, limit: int
) -> list[Row]:
    cur.execute(_JOBS_TO_SCORE, {"job_ids": job_ids, "after_id": after_id, "limit": limit})
    return fetch_all(cur)


# For each job skill: exact match on the canonical name, and the nearest profile
# skill by cosine distance. ORDER BY embedding <=> x LIMIT 1 is answered by the
# HNSW index on skill.embedding: O(log p) per skill, not a scan of all p skills.
_SKILL_HITS = """
SELECT u.skill,
       EXISTS (SELECT 1 FROM skill p WHERE p.normalized_name = u.skill) AS exact,
       nn.name AS nearest,
       nn.similarity
FROM unnest(%s::text[]) WITH ORDINALITY AS u(skill, pos)
LEFT JOIN skill_embedding e ON e.normalized_name = u.skill
LEFT JOIN LATERAL (
    SELECT p.normalized_name AS name, 1 - (p.embedding <=> e.embedding) AS similarity
    FROM skill p
    WHERE p.embedding IS NOT NULL
    ORDER BY p.embedding <=> e.embedding
    LIMIT 1
) nn ON e.embedding IS NOT NULL
ORDER BY u.pos
"""


def skill_hits(cur: Cursor, skills: list[str]) -> list[Row]:
    if not skills:
        return []
    cur.execute(_SKILL_HITS, (skills,))
    return fetch_all(cur)


def best_title_similarity(cur: Cursor, title: str, targets: list[str]) -> float | None:
    if not targets:
        return None
    cur.execute(
        "SELECT max(1 - (t.embedding <=> g.embedding)) AS sim "
        "FROM skill_embedding t, skill_embedding g "
        "WHERE t.normalized_name = %s AND g.normalized_name = ANY(%s::text[])",
        (title, targets),
    )
    row = cur.fetchone()
    return float(row["sim"]) if row and row["sim"] is not None else None


def set_title_vector(cur: Cursor, job_id: int, title_normalized: str) -> None:
    cur.execute(
        "UPDATE job j SET title_embedding = e.embedding FROM skill_embedding e "
        "WHERE j.id = %s AND e.normalized_name = %s "
        "AND j.title_embedding IS DISTINCT FROM e.embedding",
        (job_id, title_normalized),
    )


def upsert_match(cur: Cursor, job_id: int, result: MatchResult) -> None:
    cur.execute(
        """
        INSERT INTO job_match (job_id, score, passed_hard_filters, hard_fail_reasons, breakdown,
                               computed_at)
        VALUES (%(job_id)s, %(score)s, %(passed)s, %(reasons)s, %(breakdown)s, now())
        ON CONFLICT (job_id) DO UPDATE SET
            score = EXCLUDED.score, passed_hard_filters = EXCLUDED.passed_hard_filters,
            hard_fail_reasons = EXCLUDED.hard_fail_reasons, breakdown = EXCLUDED.breakdown,
            computed_at = now()
        """,
        {
            "job_id": job_id,
            "score": result.score,
            "passed": result.passed_hard_filters,
            "reasons": result.hard_fail_reasons,
            "breakdown": Json(result.breakdown),
        },
    )


# ----------------------------------------------------------------------------- shortlist

# Keyset on (score DESC, job_id): served by job_match_rank_idx when only passing jobs.
_SHORTLIST = """
SELECT j.id, j.title, j.company_id, c.name AS company_name, s.kind AS source, j.location_text,
       j.work_mode, j.employment_type, j.status, j.posted_at, j.deadline_at, j.first_seen_at,
       m.score, m.passed_hard_filters, m.hard_fail_reasons
FROM job_match m
JOIN job j ON j.id = m.job_id
JOIN company c ON c.id = j.company_id
JOIN source s ON s.id = j.source_id
WHERE (%(include_failed)s OR m.passed_hard_filters)
  AND j.status = 'active'
  AND (%(after_score)s::numeric IS NULL
       OR m.score < %(after_score)s::numeric
       OR (m.score = %(after_score)s::numeric AND m.job_id > %(after_id)s::bigint))
ORDER BY m.score DESC, m.job_id
LIMIT %(limit)s
"""


def shortlist(
    cur: Cursor, *, include_failed: bool, after: tuple[str, int] | None, limit: int
) -> list[Row]:
    cur.execute(
        _SHORTLIST,
        {
            "include_failed": include_failed,
            "after_score": after[0] if after else None,
            "after_id": after[1] if after else None,
            "limit": limit + 1,
        },
    )
    return fetch_all(cur)


def get_preferences_row(cur: Cursor) -> Row | None:
    cur.execute(
        "SELECT target_titles, work_modes, locations, excluded_companies, excluded_keywords, "
        "max_years_experience, scoring_weights, hard_filters FROM preferences WHERE id = 1"
    )
    return fetch_one(cur)
