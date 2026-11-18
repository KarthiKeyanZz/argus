from __future__ import annotations

from typing import Any

from psycopg2.extras import Json

from app.db.pool import Cursor
from app.db.sql import Row, fetch_all, fetch_one

_SUMMARY_COLUMNS = """
    j.id, j.title, j.company_id, c.name AS company_name, s.kind AS source, j.location_text,
    j.work_mode, j.employment_type, j.status, j.posted_at, j.deadline_at, j.first_seen_at,
    m.score, m.passed_hard_filters
"""

# Joins are all primary-key lookups (company.id, source.id, job_match.job_id).
_FROM = """
FROM job j
JOIN company c ON c.id = j.company_id
JOIN source s ON s.id = j.source_id
LEFT JOIN job_match m ON m.job_id = j.id
"""

# Newest-first feed with keyset pagination on (first_seen_at, id).
# With status set, this walks job_feed_idx (status, first_seen_at DESC, id DESC)
# and stops after LIMIT rows - cost does not grow with page depth.
# Full-text search uses the GIN index on the generated `search` tsvector column.
_LIST = f"""
SELECT {_SUMMARY_COLUMNS}
{_FROM}
WHERE (%(status)s::text IS NULL OR j.status = %(status)s)
  AND (%(company_id)s::bigint IS NULL OR j.company_id = %(company_id)s)
  AND (%(work_mode)s::text IS NULL OR j.work_mode = %(work_mode)s)
  AND (%(q)s::text IS NULL OR j.search @@ websearch_to_tsquery('english', %(q)s))
  AND (%(after_ts)s::timestamptz IS NULL
       OR (j.first_seen_at, j.id) < (%(after_ts)s::timestamptz, %(after_id)s::bigint))
ORDER BY j.first_seen_at DESC, j.id DESC
LIMIT %(limit)s
"""

_DETAIL = f"""
SELECT {_SUMMARY_COLUMNS},
       j.source_job_id, j.canonical_url, j.apply_url, j.department, j.description_text,
       j.salary_min, j.salary_max, j.salary_currency, j.salary_period, j.last_seen_at,
       j.closed_at, j.duplicate_of,
       CASE WHEN e.job_id IS NULL THEN NULL ELSE jsonb_build_object(
           'method', e.method, 'model', e.model, 'extractor_version', e.extractor_version,
           'required_skills', e.required_skills, 'preferred_skills', e.preferred_skills,
           'min_years_experience', e.min_years_experience,
           'max_years_experience', e.max_years_experience,
           'education_level', e.education_level, 'seniority', e.seniority,
           'employment_type', e.employment_type, 'work_mode', e.work_mode,
           'entry_level_friendly', e.entry_level_friendly, 'summary', e.summary,
           'education_fields', e.education_fields,
           'duration_ms', e.duration_ms, 'extracted_at', e.extracted_at) END AS extraction,
       CASE WHEN m.job_id IS NULL THEN NULL ELSE jsonb_build_object(
           'score', m.score, 'passed_hard_filters', m.passed_hard_filters,
           'hard_fail_reasons', m.hard_fail_reasons, 'breakdown', m.breakdown,
           'computed_at', m.computed_at) END AS match
{_FROM}
LEFT JOIN job_extraction e ON e.job_id = j.id
WHERE j.id = %s
"""

# Insert unless the (source, source_job_id) pair exists. RETURNING is empty on conflict.
_INSERT = """
INSERT INTO job (source_id, company_id, source_job_id, title, title_normalized, canonical_url,
                 apply_url, location_text, work_mode, employment_type, description_text,
                 posted_at, deadline_at, content_hash, dedupe_key, duplicate_of, raw)
VALUES (
    (SELECT id FROM source WHERE kind = %(source_kind)s),
    %(company_id)s, %(source_job_id)s, %(title)s, %(title_normalized)s, %(canonical_url)s,
    %(apply_url)s, %(location_text)s, %(work_mode)s, %(employment_type)s, %(description_text)s,
    %(posted_at)s, %(deadline_at)s, %(content_hash)s, %(dedupe_key)s,
    -- cross-source duplicate: the oldest job with the same dedupe key (job_dedupe_idx)
    (SELECT id FROM job WHERE dedupe_key = %(dedupe_key)s ORDER BY id LIMIT 1),
    %(raw)s)
ON CONFLICT (source_id, source_job_id) DO NOTHING
RETURNING id
"""

_FIND_BY_SOURCE_ID = """
SELECT j.id FROM job j JOIN source s ON s.id = j.source_id
WHERE s.kind = %s AND j.source_job_id = %s
"""

# Skill names are canonicalized through skill_alias and de-duplicated in SQL,
# keeping their original order: O(n log n) for n skills.
_CANONICAL_SKILLS = """(
    SELECT coalesce(array_agg(skill ORDER BY first_pos), '{{}}')
    FROM (
        SELECT coalesce(a.canonical, u.s) AS skill, min(u.pos) AS first_pos
        FROM unnest(%({name})s::text[]) WITH ORDINALITY AS u(s, pos)
        LEFT JOIN skill_alias a ON a.alias = u.s
        GROUP BY 1
    ) t
)"""

_UPSERT_EXTRACTION = f"""
INSERT INTO job_extraction (
    job_id, method, model, extractor_version, required_skills, preferred_skills,
    min_years_experience, max_years_experience, education_level, seniority, employment_type,
    work_mode, entry_level_friendly, summary, education_fields, raw, duration_ms, extracted_at)
VALUES (
    %(job_id)s, %(method)s, %(model)s, %(extractor_version)s,
    {_CANONICAL_SKILLS.format(name="required_skills")},
    {_CANONICAL_SKILLS.format(name="preferred_skills")},
    %(min_years)s, %(max_years)s, %(education_level)s, %(seniority)s, %(employment_type)s,
    %(work_mode)s, %(entry_level_friendly)s, %(summary)s, %(education_fields)s, %(raw)s,
    %(duration_ms)s, now())
ON CONFLICT (job_id) DO UPDATE SET
    method = EXCLUDED.method, model = EXCLUDED.model,
    extractor_version = EXCLUDED.extractor_version,
    required_skills = EXCLUDED.required_skills, preferred_skills = EXCLUDED.preferred_skills,
    min_years_experience = EXCLUDED.min_years_experience,
    max_years_experience = EXCLUDED.max_years_experience,
    education_level = EXCLUDED.education_level, seniority = EXCLUDED.seniority,
    employment_type = EXCLUDED.employment_type, work_mode = EXCLUDED.work_mode,
    entry_level_friendly = EXCLUDED.entry_level_friendly, summary = EXCLUDED.summary,
    education_fields = EXCLUDED.education_fields,
    raw = EXCLUDED.raw, duration_ms = EXCLUDED.duration_ms, extracted_at = now()
"""  # noqa: S608 - static fragments only


def list_jobs(
    cur: Cursor,
    *,
    status: str | None,
    company_id: int | None,
    work_mode: str | None,
    q: str | None,
    after: tuple[str, int] | None,
    limit: int,
) -> list[Row]:
    cur.execute(
        _LIST,
        {
            "status": status,
            "company_id": company_id,
            "work_mode": work_mode,
            "q": q,
            "after_ts": after[0] if after else None,
            "after_id": after[1] if after else None,
            "limit": limit + 1,
        },
    )
    return fetch_all(cur)


def get_detail(cur: Cursor, job_id: int) -> Row | None:
    cur.execute(_DETAIL, (job_id,))
    return fetch_one(cur)


def exists(cur: Cursor, job_id: int) -> bool:
    cur.execute("SELECT 1 FROM job WHERE id = %s", (job_id,))
    return cur.fetchone() is not None


def get_text_for_extraction(cur: Cursor, job_id: int) -> Row | None:
    cur.execute(
        "SELECT id, title, location_text, description_text FROM job WHERE id = %s", (job_id,)
    )
    return fetch_one(cur)


def insert_job(cur: Cursor, values: dict[str, Any]) -> int | None:
    """Returns the new id, or None if the job already exists for that source."""
    params = {**values, "raw": Json(values.get("raw")) if values.get("raw") is not None else None}
    cur.execute(_INSERT, params)
    row = cur.fetchone()
    return int(row["id"]) if row else None


def find_by_source_id(cur: Cursor, source_kind: str, source_job_id: str) -> int | None:
    cur.execute(_FIND_BY_SOURCE_ID, (source_kind, source_job_id))
    row = cur.fetchone()
    return int(row["id"]) if row else None


def upsert_extraction(cur: Cursor, values: dict[str, Any]) -> None:
    params = {**values, "raw": Json(values.get("raw"))}
    cur.execute(_UPSERT_EXTRACTION, params)
