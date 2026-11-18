-- =============================================================================
-- ARGUS 0001 - initial schema
--
-- Conventions
--   * bigint identity PKs (compact, ordered -> efficient B-tree + keyset paging)
--   * timestamptz everywhere, text + CHECK instead of ENUM (cheap to evolve)
--   * every foreign key has an index (a UNIQUE/PK with it as leading column counts)
--   * partial indexes for "hot subsets" (queued tasks, active jobs, ...)
--   * singletons (profile, preferences, system_state) use id = 1 + CHECK
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;             -- fuzzy / ILIKE search on names & titles
CREATE EXTENSION IF NOT EXISTS vector;              -- pgvector: embeddings + ANN indexes
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- query performance statistics

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$$;

-- Where a profile fact came from. 'llm' = machine suggestion, never trusted until verified.
CREATE DOMAIN fact_source AS text CHECK (VALUE IN ('user', 'resume', 'llm'));

-- -----------------------------------------------------------------------------
-- System: global pause, audit trail, background task queue
-- -----------------------------------------------------------------------------
CREATE TABLE system_state (
    id            smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    paused        boolean     NOT NULL DEFAULT false,
    paused_reason text,
    paused_at     timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_event (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor       text        NOT NULL CHECK (actor IN ('user', 'system', 'worker')),
    action      text        NOT NULL,
    entity_type text,
    entity_id   bigint,
    details     jsonb       NOT NULL DEFAULT '{}'
);
-- newest-first feed uses the PK (identity is monotonic); these serve the filters
CREATE INDEX audit_event_entity_idx ON audit_event (entity_type, entity_id, id DESC)
    WHERE entity_type IS NOT NULL;
CREATE INDEX audit_event_action_idx ON audit_event (action, id DESC);

CREATE TABLE task (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind         text        NOT NULL,
    payload      jsonb       NOT NULL DEFAULT '{}',
    status       text        NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    priority     smallint    NOT NULL DEFAULT 0,
    attempts     integer     NOT NULL DEFAULT 0,
    max_attempts integer     NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 20),
    run_after    timestamptz NOT NULL DEFAULT now(),
    dedupe_key   text,
    locked_by    text,
    locked_at    timestamptz,
    result       jsonb,
    last_error   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);
-- The worker's claim query walks only queued rows, already in claim order.
CREATE INDEX task_claim_idx   ON task (priority DESC, run_after, id) WHERE status = 'queued';
-- Reaper for tasks whose worker died.
CREATE INDEX task_running_idx ON task (locked_at) WHERE status = 'running';
-- At most one live task per dedupe key (e.g. 'job.extract:42').
CREATE UNIQUE INDEX task_dedupe_live_uq ON task (dedupe_key)
    WHERE dedupe_key IS NOT NULL AND status IN ('queued', 'running');
CREATE INDEX task_status_feed_idx ON task (status, id DESC);

-- -----------------------------------------------------------------------------
-- Career profile (single user)
-- -----------------------------------------------------------------------------
CREATE TABLE profile (
    id                       smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    full_name                text,
    email                    text,
    phone                    text,
    location                 text,
    headline                 text,
    summary                  text,
    linkedin_url             text,
    github_url               text,
    portfolio_url            text,
    website_url              text,
    work_authorization       text,
    requires_sponsorship     boolean,
    notice_period            text,
    available_from           date,
    expected_salary_min      numeric(12, 2) CHECK (expected_salary_min >= 0),
    expected_salary_currency char(3),
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resume_file (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_filename text        NOT NULL,
    stored_name       text        NOT NULL UNIQUE,
    mime_type         text        NOT NULL,
    size_bytes        integer     NOT NULL CHECK (size_bytes > 0),
    sha256            char(64)    NOT NULL UNIQUE,
    is_master         boolean     NOT NULL DEFAULT false,
    extracted_text    text,
    uploaded_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX resume_file_single_master_uq ON resume_file (is_master) WHERE is_master;

CREATE TABLE education (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    institution    text        NOT NULL,
    degree         text,
    field_of_study text,
    start_date     date,
    end_date       date,
    grade          text,
    source         fact_source NOT NULL DEFAULT 'user',
    source_ref     text,
    verified       boolean     NOT NULL DEFAULT false,
    sort_order     integer     NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date IS NULL OR start_date IS NULL OR start_date <= end_date)
);

CREATE TABLE experience (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company         text        NOT NULL,
    title           text        NOT NULL,
    employment_type text CHECK (employment_type IN
                    ('full_time', 'part_time', 'internship', 'contract', 'freelance', 'apprenticeship')),
    location        text,
    start_date      date,
    end_date        date,
    is_current      boolean     NOT NULL DEFAULT false,
    description     text,
    source          fact_source NOT NULL DEFAULT 'user',
    source_ref      text,
    verified        boolean     NOT NULL DEFAULT false,
    sort_order      integer     NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date IS NULL OR start_date IS NULL OR start_date <= end_date)
);

CREATE TABLE project (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text        NOT NULL,
    description text,
    url         text,
    tech        text[]      NOT NULL DEFAULT '{}',
    start_date  date,
    end_date    date,
    source      fact_source NOT NULL DEFAULT 'user',
    source_ref  text,
    verified    boolean     NOT NULL DEFAULT false,
    sort_order  integer     NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Resume bullet points. Tailored resumes *select* from verified achievements; they never invent.
CREATE TABLE achievement (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    experience_id bigint REFERENCES experience (id) ON DELETE CASCADE,
    project_id    bigint REFERENCES project (id) ON DELETE CASCADE,
    text          text        NOT NULL,
    source        fact_source NOT NULL DEFAULT 'user',
    source_ref    text,
    verified      boolean     NOT NULL DEFAULT false,
    sort_order    integer     NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(experience_id, project_id) = 1)
);
CREATE INDEX achievement_experience_idx ON achievement (experience_id) WHERE experience_id IS NOT NULL;
CREATE INDEX achievement_project_idx    ON achievement (project_id)    WHERE project_id IS NOT NULL;

CREATE TABLE certification (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           text        NOT NULL,
    issuer         text,
    issued_on      date,
    expires_on     date,
    credential_url text,
    source         fact_source NOT NULL DEFAULT 'user',
    source_ref     text,
    verified       boolean     NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE skill (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name             text        NOT NULL,
    normalized_name  text        NOT NULL UNIQUE,
    category         text,
    proficiency      text CHECK (proficiency IN ('beginner', 'intermediate', 'advanced', 'expert')),
    years_experience numeric(4, 1) CHECK (years_experience >= 0),
    source           fact_source NOT NULL DEFAULT 'user',
    source_ref       text,
    verified         boolean     NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- Synonyms: 'js' -> 'javascript'. Shared by profile skills and job requirements.
CREATE TABLE skill_alias (
    alias     text PRIMARY KEY,
    canonical text NOT NULL
);
CREATE INDEX skill_alias_canonical_idx ON skill_alias (canonical);

-- -----------------------------------------------------------------------------
-- Preferences & reusable answers
-- -----------------------------------------------------------------------------
CREATE TABLE preferences (
    id                   smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    target_titles        text[]      NOT NULL DEFAULT '{}',
    experience_levels    text[]      NOT NULL DEFAULT '{}'
        CHECK (experience_levels <@ ARRAY['fresher', 'internship', 'entry', 'junior', 'associate']),
    min_years_experience numeric(4, 1) CHECK (min_years_experience >= 0),
    max_years_experience numeric(4, 1) CHECK (max_years_experience >= 0),
    locations            text[]      NOT NULL DEFAULT '{}',
    countries            text[]      NOT NULL DEFAULT '{}',
    work_modes           text[]      NOT NULL DEFAULT '{}'
        CHECK (work_modes <@ ARRAY['remote', 'hybrid', 'onsite']),
    employment_types     text[]      NOT NULL DEFAULT '{}',
    excluded_companies   text[]      NOT NULL DEFAULT '{}',
    excluded_keywords    text[]      NOT NULL DEFAULT '{}',
    willing_to_relocate  boolean,
    min_salary           numeric(12, 2) CHECK (min_salary >= 0),
    salary_currency      char(3),
    scoring_weights      jsonb       NOT NULL DEFAULT '{}',
    hard_filters         jsonb       NOT NULL DEFAULT '{}',
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (min_years_experience IS NULL OR max_years_experience IS NULL
           OR min_years_experience <= max_years_experience)
);

CREATE TABLE answer_library (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question            text        NOT NULL,
    question_normalized text        NOT NULL UNIQUE,
    answer              text        NOT NULL,
    kind                text        NOT NULL DEFAULT 'exact' CHECK (kind IN ('exact', 'derived')),
    tags                text[]      NOT NULL DEFAULT '{}',
    approved            boolean     NOT NULL DEFAULT false,
    use_count           integer     NOT NULL DEFAULT 0,
    last_used_at        timestamptz,
    embedding           vector(768),  -- nomic-embed-text dimension
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX answer_library_question_trgm ON answer_library USING gin (question_normalized gin_trgm_ops);
CREATE INDEX answer_library_embedding_hnsw ON answer_library USING hnsw (embedding vector_cosine_ops);

-- -----------------------------------------------------------------------------
-- Sources, companies, jobs
-- -----------------------------------------------------------------------------
CREATE TABLE source (
    id                    smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind                  text        NOT NULL UNIQUE
        CHECK (kind IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'manual')),
    name                  text        NOT NULL,
    access_method         text        NOT NULL CHECK (access_method IN ('public_api', 'manual')),
    api_base_url          text,
    terms_url             text,
    permitted_use         text,
    rate_limit_per_minute integer     NOT NULL DEFAULT 30 CHECK (rate_limit_per_minute > 0),
    discovery_enabled     boolean     NOT NULL DEFAULT true,
    auto_apply_enabled    boolean     NOT NULL DEFAULT false,
    last_checked_at       timestamptz,
    notes                 text,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE company (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name               text        NOT NULL,
    normalized_key     text        NOT NULL UNIQUE,
    website_url        text,
    careers_url        text,
    ats_kind           text REFERENCES source (kind),
    ats_token          text,
    enabled            boolean     NOT NULL DEFAULT true,
    notes              text,
    last_discovered_at timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CHECK ((ats_kind IS NULL) = (ats_token IS NULL))
);
CREATE UNIQUE INDEX company_ats_uq ON company (ats_kind, ats_token) WHERE ats_kind IS NOT NULL;
CREATE INDEX company_name_trgm ON company USING gin (name gin_trgm_ops);
-- "which company should discovery crawl next": least recently crawled first
CREATE INDEX company_crawl_queue_idx ON company (last_discovered_at NULLS FIRST, id)
    WHERE enabled AND ats_kind IS NOT NULL;

CREATE TABLE discovery_run (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id     smallint    NOT NULL REFERENCES source (id),
    company_id    bigint REFERENCES company (id) ON DELETE CASCADE,
    status        text        NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'failed', 'blocked')),
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    fetched_count integer     NOT NULL DEFAULT 0,
    new_count     integer     NOT NULL DEFAULT 0,
    updated_count integer     NOT NULL DEFAULT 0,
    closed_count  integer     NOT NULL DEFAULT 0,
    error         text
);
CREATE INDEX discovery_run_company_idx ON discovery_run (company_id, started_at DESC);
CREATE INDEX discovery_run_source_idx  ON discovery_run (source_id, started_at DESC);

CREATE TABLE job (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id        smallint    NOT NULL REFERENCES source (id),
    company_id       bigint      NOT NULL REFERENCES company (id) ON DELETE CASCADE,
    source_job_id    text        NOT NULL,
    title            text        NOT NULL,
    title_normalized text        NOT NULL,
    canonical_url    text        NOT NULL,
    apply_url        text,
    location_text    text,
    work_mode        text        NOT NULL DEFAULT 'unknown'
        CHECK (work_mode IN ('remote', 'hybrid', 'onsite', 'unknown')),
    employment_type  text,
    department       text,
    description_text text        NOT NULL DEFAULT '',
    description_html text,        -- sanitized before storage
    salary_min       numeric(12, 2),
    salary_max       numeric(12, 2),
    salary_currency  char(3),
    salary_period    text CHECK (salary_period IN ('hour', 'day', 'month', 'year')),
    posted_at        timestamptz,
    deadline_at      timestamptz,
    status           text        NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'closed', 'expired', 'uncertain')),
    content_hash     char(64)    NOT NULL,
    dedupe_key       char(40)    NOT NULL,
    duplicate_of     bigint REFERENCES job (id) ON DELETE SET NULL,
    first_seen_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at     timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,
    raw              jsonb,
    search           tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A')
        || setweight(to_tsvector('english', coalesce(location_text, '')), 'C')
        || setweight(to_tsvector('english', left(description_text, 100000)), 'B')
    ) STORED,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, source_job_id),  -- upsert target; also covers the source_id FK
    CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)
);
-- Main feed: newest jobs by status, keyset-paginated on (first_seen_at, id).
CREATE INDEX job_feed_idx          ON job (status, first_seen_at DESC, id DESC);
CREATE INDEX job_company_idx       ON job (company_id, status);
CREATE INDEX job_search_gin        ON job USING gin (search);
CREATE INDEX job_title_trgm        ON job USING gin (title_normalized gin_trgm_ops);
CREATE INDEX job_dedupe_idx        ON job (dedupe_key);
CREATE INDEX job_canonical_url_idx ON job (canonical_url);
CREATE INDEX job_duplicate_of_idx  ON job (duplicate_of) WHERE duplicate_of IS NOT NULL;
CREATE INDEX job_deadline_idx      ON job (deadline_at) WHERE status = 'active' AND deadline_at IS NOT NULL;

CREATE TABLE job_extraction (
    job_id               bigint PRIMARY KEY REFERENCES job (id) ON DELETE CASCADE,
    method               text        NOT NULL CHECK (method IN ('rules', 'llm')),
    model                text,
    extractor_version    integer     NOT NULL,
    required_skills      text[]      NOT NULL DEFAULT '{}',
    preferred_skills     text[]      NOT NULL DEFAULT '{}',
    min_years_experience numeric(4, 1),
    max_years_experience numeric(4, 1),
    education_level      text,
    seniority            text,
    employment_type      text,
    work_mode            text,
    entry_level_friendly boolean,
    summary              text,
    raw                  jsonb,
    duration_ms          integer,
    extracted_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX job_extraction_required_skills_gin ON job_extraction USING gin (required_skills);
CREATE INDEX job_extraction_min_years_idx       ON job_extraction (min_years_experience);

CREATE TABLE job_match (
    job_id              bigint PRIMARY KEY REFERENCES job (id) ON DELETE CASCADE,
    score               numeric(5, 2) NOT NULL CHECK (score BETWEEN 0 AND 100),
    passed_hard_filters boolean       NOT NULL,
    hard_fail_reasons   text[]        NOT NULL DEFAULT '{}',
    breakdown           jsonb         NOT NULL DEFAULT '{}',
    computed_at         timestamptz   NOT NULL DEFAULT now()
);
-- Ranked shortlist reads only the eligible subset, already sorted.
CREATE INDEX job_match_rank_idx ON job_match (score DESC, job_id) WHERE passed_hard_filters;

-- -----------------------------------------------------------------------------
-- Applications
-- -----------------------------------------------------------------------------
CREATE TABLE application (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id           bigint      NOT NULL UNIQUE REFERENCES job (id) ON DELETE RESTRICT,
    state            text        NOT NULL DEFAULT 'saved' CHECK (state IN (
        'saved', 'queued', 'preparing', 'needs_input', 'ready', 'submitting',
        'awaiting_captcha', 'awaiting_otp', 'submitted_confirmed', 'submission_unknown', 'failed',
        'assessment', 'interview', 'offer', 'rejected', 'withdrawn', 'no_response')),
    notes            text,
    state_changed_at timestamptz NOT NULL DEFAULT now(),
    submitted_at     timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX application_state_idx ON application (state, state_changed_at DESC);

CREATE TABLE application_event (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id bigint      NOT NULL REFERENCES application (id) ON DELETE CASCADE,
    from_state     text,
    to_state       text        NOT NULL,
    actor          text        NOT NULL CHECK (actor IN ('user', 'system', 'worker')),
    evidence       jsonb       NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX application_event_app_idx ON application_event (application_id, id DESC);

-- -----------------------------------------------------------------------------
-- updated_at triggers (fire only when something actually changed)
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'system_state', 'profile', 'education', 'experience', 'project', 'achievement',
        'certification', 'skill', 'preferences', 'answer_library', 'source', 'company',
        'application'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW '
            'WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION set_updated_at()',
            t || '_set_updated_at', t);
    END LOOP;
END
$$;

-- job has a generated column, which a BEFORE trigger's WHEN clause may not read.
-- No-op updates are avoided at the source instead: upserts only touch a row when
-- content_hash changed (ON CONFLICT ... DO UPDATE ... WHERE ... IS DISTINCT FROM ...).
CREATE TRIGGER job_set_updated_at BEFORE UPDATE ON job
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
