-- =============================================================================
-- ARGUS 0003 - semantic skill matching + more synonyms
-- =============================================================================

-- Embedding cache keyed by canonical skill name: every distinct skill string is
-- embedded once and reused by every job / profile that mentions it.
CREATE TABLE skill_embedding (
    normalized_name text PRIMARY KEY,
    model           text        NOT NULL,
    embedding       vector(768) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Profile skills get their own vector so "nearest profile skill to X" is an
-- index lookup (HNSW, cosine) instead of comparing X with every skill.
ALTER TABLE skill ADD COLUMN embedding vector(768);
CREATE INDEX skill_embedding_hnsw ON skill USING hnsw (embedding vector_cosine_ops);

-- Job title vector for title-vs-target-role similarity.
ALTER TABLE job ADD COLUMN title_embedding vector(768);

-- Extraction prompt v2 separates degree fields from skills.
ALTER TABLE job_extraction ADD COLUMN education_fields text[] NOT NULL DEFAULT '{}';

INSERT INTO skill_alias (alias, canonical) VALUES
    ('rest apis', 'rest api'), ('apis', 'api'), ('restful apis', 'rest api'), ('web apis', 'rest api'),
    ('data structures', 'data structures and algorithms'),
    ('algorithms', 'data structures and algorithms'),
    ('data structures & algorithms', 'data structures and algorithms'),
    ('oops', 'object oriented programming'), ('object-oriented programming', 'object oriented programming'),
    ('object oriented design', 'object oriented programming'),
    ('object-oriented design', 'object oriented programming'),
    ('machine learning basics', 'machine learning'), ('ml basics', 'machine learning'),
    ('postgres database', 'postgresql'), ('postgresql database', 'postgresql'),
    ('mysql database', 'mysql'), ('ms sql', 'sql server'), ('mssql', 'sql server'),
    ('unix', 'linux'), ('shell scripting', 'bash'), ('shell', 'bash'),
    ('git/github', 'git'), ('github', 'git'), ('version control', 'git'),
    ('unit testing', 'testing'), ('automated testing', 'testing'),
    ('containers', 'docker'), ('containerization', 'docker'),
    ('amazon aws', 'amazon web services'), ('google cloud platform', 'google cloud'),
    ('microsoft azure', 'azure'),
    ('llm', 'large language models'), ('llms', 'large language models'),
    ('gen-ai', 'generative ai'),
    ('ci', 'ci cd'), ('continuous integration', 'ci cd'),
    ('js frameworks', 'javascript frameworks'),
    ('html/css', 'html css'), ('html & css', 'html css'),
    ('numpy library', 'numpy'), ('pandas library', 'pandas')
ON CONFLICT (alias) DO NOTHING;

-- 0002 mapped llm/llms -> 'llm'; point them at the new canonical name too.
UPDATE skill_alias SET canonical = 'large language models' WHERE alias IN ('llms', 'large language models')
    AND canonical = 'llm';
DELETE FROM skill_alias WHERE alias = 'large language models';

-- Re-canonicalize existing profile skills with the new aliases. Where several rows
-- map to the same canonical name, keep one (prefer the row already canonical).
WITH mapped AS (
    SELECT s.id,
           COALESCE(a.canonical, s.normalized_name) AS target,
           (a.alias IS NULL) AS already_canonical
    FROM skill s
    LEFT JOIN skill_alias a ON a.alias = s.normalized_name
), ranked AS (
    SELECT id, row_number() OVER (PARTITION BY target ORDER BY already_canonical DESC, id) AS rn
    FROM mapped
)
DELETE FROM skill WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

UPDATE skill s SET normalized_name = a.canonical, embedding = NULL
FROM skill_alias a WHERE a.alias = s.normalized_name;
