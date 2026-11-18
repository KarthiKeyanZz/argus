# 01 — ARGUS overview

*100 eyes. Thousands of opportunities. One career.*

## The goal

ARGUS is a personal, **local-first** job-search assistant. It aims to:

1. **Discover** fresher / early-career jobs from permitted sources.
2. **Understand** each posting (skills, years, education, work mode) with a local LLM.
3. **Match** postings against your **verified** profile and explain the score.
4. **Prepare** truthful applications (answers, tailored resume) — upcoming.
5. **Apply automatically** within your rules, pausing for CAPTCHAs — upcoming.
6. **Track** responses through Gmail, including verification codes (OTPs) — upcoming.

All of it free, on your own machine, without inventing anything about you.

---

## Architecture

```
┌──────────────────────── your machine (127.0.0.1 only) ────────────────────────┐
│                                                                              │
│  Browser ── React UI (Vite :5173) ──/api──► FastAPI (:8000, Swagger /docs)    │
│                                               │                              │
│                                               │ raw SQL (psycopg2)            │
│                                               ▼                              │
│                         PostgreSQL 18 + pgvector (:5433, container)          │
│                           ▲   tables, indexes, vectors, task queue           │
│                           │                                                  │
│                     worker process ── LISTEN/NOTIFY wake-ups                 │
│                           │                                                  │
│                           ▼                                                  │
│                  Ollama (:11434, systemd user service, GPU)                  │
│                   ├─ gemma4:26b-a4b-it-qat   (reads & writes text)           │
│                   └─ nomic-embed-text        (turns text into vectors)       │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Component | Tech | Role |
|---|---|---|
| UI | React 19, TypeScript, Vite, Tailwind, TanStack Query | Screens: dashboard, jobs, profile, preferences, companies, activity, LLM Lab |
| API | FastAPI + Pydantic | Validation, Swagger docs, short requests |
| Database | PostgreSQL 18 + pgvector, raw SQL | Profile, jobs, matches, embeddings, task queue, audit trail |
| Worker | Python process | Slow work: LLM extraction, scoring, warm-up |
| LLM server | Ollama (llama.cpp inside) | Runs the models on your GPU |

Why the **worker** exists: LLM calls take seconds. The API stays fast by queuing a task; the
worker picks it up, runs the model, saves the result, and the UI polls the task status.

---

## Data flow of one job (today)

```
1. Job enters ARGUS             (manually today; automatic discovery = next milestone)
2. POST /jobs/{id}/extract ──► task queue ──► worker
3. worker: Gemma reads the posting → JobFacts JSON (skills, years, seniority…)
4. worker: saves extraction, queues "match.job"
5. worker: embeddings + nearest-neighbour skill matching + weights + hard filters → score
6. UI: Jobs → Best matches; Job page explains the score
```

## Data flow of your resume

```
upload PDF/DOCX ──► safety checks + local text extraction ──► stored (0600)
"Read with LLM" ──► Gemma → ResumeFacts draft (nothing saved yet)
you review/edit in the UI ──► Import ──► profile, experience, education, projects, skills
```

---

## Codebase map

```
ai-bot/
├── docs/                         original brief, guardrails, decision log, quick LLM notes
├── study/                        ← this course
└── argus/
    ├── Makefile                  every command (make help)
    ├── compose.yaml              PostgreSQL + pgvector container
    ├── llm/Modelfile.extractor   tuned model variant
    ├── backend/app/
    │   ├── main.py               app factory, middleware, Swagger
    │   ├── core/                 config, logging + redaction, errors, security middleware
    │   ├── db/                   connection pool, migration runner, migrations/*.sql
    │   ├── modules/              one folder per feature:
    │   │   ├── llm/              Ollama client, prompts, schemas, structured output
    │   │   ├── resume/           upload safety, parse, import
    │   │   ├── matching/         scoring (pure), embeddings cache, shortlist
    │   │   ├── jobs/ companies/ profile/ preferences/ tasks/ system/ audit/ health/
    │   └── worker/               task loop + handlers
    └── frontend/src/             api/ (typed client), components/, pages/, lib/
```

Every feature module follows `router.py` (HTTP) → `service.py` (use case, transactions) →
`repository.py` (SQL), with `schemas.py` for validation.

---

## Engineering rules (and why)

| Rule | Why |
|---|---|
| Raw parameterized SQL, no ORM | Full control of queries and indexes; safe from SQL injection |
| No O(n²) code; keyset pagination | Stays fast as data grows |
| Never hold a DB connection during an LLM call | LLM calls take seconds; the pool would starve |
| LLM = pure function, no tools | Prompt injection can't make it *do* anything |
| Never invent facts | Guardrail: truthful applications only |
| Everything audited, personal values never logged | Accountability + privacy |

## Where to go next

- Why and where the LLM is used: [02](02-why-and-where-llms-in-argus.md)
- Each LLM workflow in detail: [03](03-llm-workflows-in-argus.md)
- What's left to build: [09](09-roadmap-and-remaining-work.md)
