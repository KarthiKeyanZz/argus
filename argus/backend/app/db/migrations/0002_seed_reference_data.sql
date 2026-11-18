-- =============================================================================
-- ARGUS 0002 - reference data (idempotent)
-- =============================================================================

INSERT INTO system_state (id, paused) VALUES (1, false)
ON CONFLICT (id) DO NOTHING;

-- Source registry. last_checked_at stays NULL until the terms are reviewed;
-- auto_apply_enabled is OFF for every source until explicitly turned on.
INSERT INTO source (kind, name, access_method, api_base_url, rate_limit_per_minute,
                    discovery_enabled, notes)
VALUES
    ('greenhouse', 'Greenhouse Job Board API', 'public_api',
     'https://boards-api.greenhouse.io/v1/boards', 30, true,
     'Public, unauthenticated GET API. ?questions=true exposes application form fields.'),
    ('lever', 'Lever Postings API', 'public_api',
     'https://api.lever.co/v0/postings', 30, true,
     'Public, unauthenticated GET API (?mode=json). Apply pages load hCaptcha.'),
    ('ashby', 'Ashby Job Posting API', 'public_api',
     'https://api.ashbyhq.com/posting-api/job-board', 30, true,
     'Public, unauthenticated GET API. Apply pages load reCAPTCHA.'),
    ('smartrecruiters', 'SmartRecruiters Posting API', 'public_api',
     'https://api.smartrecruiters.com/v1/companies', 30, false,
     'Disabled until verified.'),
    ('manual', 'Manually added', 'manual', NULL, 60, true,
     'Jobs pasted in by the user (e.g. from portals that forbid automation).')
ON CONFLICT (kind) DO NOTHING;

-- Common skill synonyms (alias -> canonical). Keys are already normalized.
INSERT INTO skill_alias (alias, canonical) VALUES
    ('js', 'javascript'), ('ecmascript', 'javascript'), ('es6', 'javascript'),
    ('ts', 'typescript'),
    ('py', 'python'), ('python3', 'python'),
    ('golang', 'go'),
    ('node', 'node.js'), ('nodejs', 'node.js'), ('node js', 'node.js'),
    ('reactjs', 'react'), ('react.js', 'react'), ('react js', 'react'),
    ('vuejs', 'vue'), ('vue.js', 'vue'),
    ('nextjs', 'next.js'), ('next js', 'next.js'),
    ('angularjs', 'angular'),
    ('postgres', 'postgresql'), ('psql', 'postgresql'), ('pg', 'postgresql'),
    ('mongo', 'mongodb'),
    ('k8s', 'kubernetes'),
    ('aws', 'amazon web services'), ('gcp', 'google cloud'), ('azure cloud', 'azure'),
    ('ml', 'machine learning'), ('dl', 'deep learning'),
    ('nlp', 'natural language processing'), ('cv', 'computer vision'),
    ('llms', 'llm'), ('large language models', 'llm'),
    ('genai', 'generative ai'), ('gen ai', 'generative ai'),
    ('sklearn', 'scikit-learn'), ('scikit learn', 'scikit-learn'),
    ('tf', 'tensorflow'),
    ('c sharp', 'c#'), ('csharp', 'c#'),
    ('cpp', 'c++'),
    ('dotnet', '.net'), ('.net core', '.net'),
    ('rest', 'rest api'), ('restful', 'rest api'), ('restful api', 'rest api'),
    ('ci/cd', 'ci cd'), ('cicd', 'ci cd'),
    ('oop', 'object oriented programming'),
    ('dsa', 'data structures and algorithms'),
    ('html5', 'html'), ('css3', 'css'),
    ('tailwindcss', 'tailwind css'), ('tailwind', 'tailwind css'),
    ('springboot', 'spring boot'),
    ('gh actions', 'github actions')
ON CONFLICT (alias) DO NOTHING;
