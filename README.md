# ARGUS

*100 eyes. Thousands of opportunities. One career.*

ARGUS is a local-first job search assistant. It reads your resume and job postings with a
locally running LLM, works out each job's real requirements, and ranks every job against your
verified profile with a score that explains itself. Everything runs on your own machine, so
personal data never leaves it, and the whole stack is free to run.

> Status: active development. Profile, resume parsing, job understanding and explainable
> matching work end to end. Automatic job discovery, an application tracker, Gmail integration
> and application automation are next (see [Roadmap](#roadmap)).

---

## Features

- **Resume import**: upload a PDF or DOCX, parse it locally with an LLM, review and correct every
  field, then import it into a structured profile (experience, education, projects, skills).
- **Job understanding**: an LLM extracts required and preferred skills, years of experience,
  education, seniority, work mode and whether freshers are welcome. Output is constrained to a
  JSON Schema.
- **Explainable matching**: skill synonyms, embedding similarity (pgvector, HNSW), weighted score
  components and hard filters. Each job shows exactly why it scored what it did.
- **Preferences**: target titles, locations, work modes, exclusions, score weights and hard filters.
- **Privacy and safety**: local inference, PII-redacted logs, audit trail, data export and
  deletion, loopback-only services, prompt-injection defences, safe file uploads.
- **LLM Lab**: a built-in playground for experimenting with sampling settings, context size,
  reasoning mode, JSON mode and embeddings, with live speed metrics.

## Architecture

```
React UI (Vite)  ──/api──►  FastAPI (Swagger at /docs)
                               │  raw parameterized SQL (psycopg2)
                               ▼
                    PostgreSQL 18 + pgvector  ◄── task queue (LISTEN/NOTIFY, SKIP LOCKED)
                               ▲
                        background worker
                               │
                               ▼
                 Ollama: gemma4:26b-a4b-it-qat (text)  ·  nomic-embed-text (embeddings)
```

Slow LLM work (extraction, scoring) runs in the worker, so the API stays fast. The LLM is used
as a pure function: it reads untrusted text and fills a fixed schema, with no tools and no
decision-making. Code validates its output, does all arithmetic and applies the scoring rules.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic, psycopg2 (no ORM), uv |
| Database | PostgreSQL 18, pgvector (HNSW), pg_trgm, full-text search |
| LLM | Ollama, Gemma 4 26B (mixture-of-experts, 4-bit QAT), nomic-embed-text |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, typed OpenAPI client |
| Quality | pytest, ruff, mypy (strict), ESLint, Vitest |
| Infra | Podman/Docker Compose (database), systemd user service (Ollama) |

## Getting started

### Prerequisites

- Linux or macOS, Python 3.13 via [uv](https://docs.astral.sh/uv/), Node.js 22+
- Podman or Docker with Compose
- [Ollama](https://ollama.com) 0.40+; an NVIDIA GPU with 12 GB VRAM is recommended (CPU works, slowly)

### Setup

```bash
cd argus
make env           # creates .env with a random database password (git-ignored)
make db-up         # PostgreSQL + pgvector on 127.0.0.1:5433
make install       # backend dependencies
make migrate       # database schema
make web-install   # frontend dependencies

ollama serve &     # or run Ollama as a service
make llm-pull      # gemma4:26b-a4b-it-qat (~15 GB) + nomic-embed-text
```

### Run

```bash
make api       # terminal 1: API at http://127.0.0.1:8000/docs
make worker    # terminal 2: background worker
make web       # terminal 3: UI at http://127.0.0.1:5173
```

### Quality checks

```bash
make check-all   # ruff, mypy, pytest, tsc, eslint, vitest, production build
make test-llm    # optional: tests against the real local model
```

Run `make help` to see every command.

## Repository layout

```
.
├── argus/
│   ├── backend/        FastAPI app, worker, SQL migrations, tests
│   ├── frontend/       React app
│   ├── llm/            Ollama Modelfile for a tuned extractor variant
│   ├── compose.yaml    PostgreSQL + pgvector
│   └── Makefile        all developer commands
└── docs/
    ├── ARGUS_*.md      product brief, guardrails, decision log and milestones
    ├── learning/       LLM quick reference written during the build
    └── study/          a course: LLM theory, and how ARGUS applies it
```

More detail on the code structure and conventions: [`argus/README.md`](argus/README.md).

## Responsible automation

ARGUS only uses official public job-board APIs and pages that allow access. It does not scrape
or automate sites whose terms forbid it (such as LinkedIn, Naukri and Indeed), never solves or
bypasses CAPTCHAs, and never invents qualifications. Jobs from those portals can still be added
by hand.

## Roadmap

| Milestone | Status |
|---|---|
| Backend foundation, local LLM integration | Done |
| Resume upload, parsing, review and import | Done |
| Explainable matching and shortlist | Done |
| React UI | Done |
| Automatic job discovery (Greenhouse, Lever, Ashby, Adzuna, Remotive) | Next |
| Application tracker | Planned |
| LLM evaluation harness and model comparison | Planned |
| Application preparation (answer library, tailored resume, cover letters) | Planned |
| Application automation with CAPTCHA pause | Planned |
| Gmail integration (status updates, verification codes) | Planned |
| Fine-tuning a smaller extraction model (QLoRA) | Planned |
