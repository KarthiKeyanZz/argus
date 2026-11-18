# 03 — The LLM workflows in ARGUS, step by step

Each workflow below shows the request path, the exact prompt/schema ideas, the safety measures,
and the files to read.

---

## Workflow A — Job posting extraction

**Trigger:** `POST /api/v1/jobs/{id}/extract` (UI: job page → "Extract with LLM"), or
automatically for new jobs.

```
API ─ enqueue task "job.extract" (dedupe key job.extract:{id}) ─ NOTIFY ─► worker wakes up
worker:
  1. short DB transaction: read title + location + description
  2. NO DB connection held ───► Ollama /api/chat
        system:  JOB_EXTRACTION_SYSTEM (rules, "untrusted data", few-shot example)  ← prompt v2
        user:    "Extract the facts…  <<<POSTING {fenced text} POSTING>>>"
        format:  llm_schema(JobFacts)    ← all keys required, enums, maxItems 30
        options: temperature 0, seed 7, num_ctx 8192, num_predict 1536
        think:   false
  3. reject if done_reason == "length" (truncated / looping)
  4. Pydantic validation → JobFacts
  5. clean_job_facts(): lower-case, de-dupe, drop non-skills, move degree subjects
  6. short DB transaction: upsert job_extraction
        - skills canonicalized in SQL via skill_alias (js → javascript), order kept
  7. enqueue "match.job" for this job  → Workflow C
```

**`JobFacts` field order** (on purpose): title → summary → education_level →
education_fields → min/max years → seniority → entry_level_friendly → required_skills →
preferred_skills → employment_type → work_mode → location.

**Measured:** 4–9 s per posting, ~45–56 tokens/s, 8 real postings in 47 s.

**Files:** `app/modules/llm/{prompts,schemas,service,structured}.py`,
`app/worker/handlers.py` (`job_extract`), `app/modules/jobs/repository.py`
(`_UPSERT_EXTRACTION`).

---

## Workflow B — Resume parsing and import

```
1. POST /resumes (multipart)
     - size ≤ 5 MB, type from magic bytes (%PDF / PK zip), DOCX must contain word/document.xml,
       zip-bomb + macro checks, SHA-256 dedupe
     - text extracted locally (pypdf / python-docx), stored with random name, 0600 perms
2. POST /resumes/{id}/parse            (synchronous, ~12–13 s)
     system:  RESUME_SYSTEM ("copy exactly", "never calculate", date format rules)
     format:  llm_schema(ResumeFacts)
                 dates: pattern ^((Jan|…|Dec) )?YYYY$  or  "Present"
                 lists: maxItems (education 6, experience 12, projects 12, skills 60)
     options: temperature 0, seed 7, num_predict 4096, think false
   post-processing in code:
     - skills normalized/de-duplicated
     - URLs get https:// if missing (linkedin.com/in/x → https://linkedin.com/in/x)
     - months per role computed from dates (Jun 2025 – Aug 2025 = 3)
   → returns a DRAFT. Nothing is saved.
3. You review and edit the draft in the UI.
4. POST /resumes/{id}/import
     - profile fields filled only where the resume provides them
     - previous resume-imported rows replaced (optional)
     - experience → achievements (bullets) linked by sort_order, not by guessing order
     - skills bulk-inserted with synonym mapping; source = "resume", verified = you reviewed
```

**Why parse and import are separate:** the LLM can be wrong, so a human-in-the-loop review is
the grounding step ([theories/08](../theories/08-rag-grounding-hallucination.md)).

**Files:** `app/modules/resume/{files,schemas,service,dates,router}.py`,
`frontend/src/pages/profile/ResumeImport.tsx`.

---

## Workflow C — Matching and scoring

```
match.job / match.all task
  1. refresh_profile_vectors(): embed profile skills that have no vector yet (cache first)
  2. load preferences → Prefs (weights, hard filters, target titles…)
  3. for each batch of 100 jobs (keyset pagination):
       - ONE batched embedding pass for all new texts (skills, titles, target titles)
       - per job: SQL per skill
            exact?   = skill name exists in your profile
            nearest  = ORDER BY embedding <=> x LIMIT 1   (HNSW index)
       - score_job(): pure function → components, weights, hard-filter reasons
       - upsert job_match (score, passed, reasons, breakdown JSON)
```

Details and calibration: [05 — Matching engine](05-matching-engine.md).

**Files:** `app/modules/matching/{scoring,service,repository}.py`.

---

## Workflow D — LLM Lab (learning)

`/api/v1/llm/generate`, `/chat`, `/embed`, `/similarity`, `/models`, `/models/{name}` expose the
raw building blocks with every option and timing metric. The UI page **LLM Lab** wraps them
with explanations. Nothing in the Lab touches your data.

---

## Shared building blocks

| Block | Where | What it guarantees |
|---|---|---|
| `OllamaClient` | `llm/client.py` | Raw HTTP to Ollama; maps errors to 404/502/503 with helpful hints |
| `llm_schema()` | `llm/structured.py` | Every key required in the grammar |
| `metrics_from()` | `llm/service.py` | ns → ms, tokens/s |
| `fence()` / `fence_resume()` | `llm/prompts.py` | Neutralize fake markers in untrusted text |
| Prompt versions | `JOB_EXTRACTION_VERSION`, `RESUME_EXTRACTION_VERSION` | Results traceable to the prompt used |
| Task queue | `tasks/repository.py` | One live task per dedupe key; retries with backoff; SKIP LOCKED |

---

## Sequence: from clicking "Extract" to seeing a score

```
UI            API              Postgres              Worker               Ollama
 │ click ──────►│ enqueue ──────►│ INSERT task + NOTIFY ►│ (wakes)
 │◄── task id ──│                │                      │ claim (SKIP LOCKED)
 │ poll task ──►│                │◄─ read job ──────────│
 │              │                │                      │── chat(JobFacts) ──►│ ~5 s
 │              │                │◄─ save extraction ───│◄──── JSON ──────────│
 │              │                │◄─ enqueue match.job ─│
 │              │                │                      │── embed(new texts) ►│ <1 s
 │              │                │◄─ HNSW lookups, save score ─│
 │◄── done ─────│                │                      │
 │ refetch job ►│── job + extraction + match ──► UI shows "Why this score"
```
