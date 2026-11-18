# ARGUS

*100 eyes. Thousands of opportunities. One career.*

ARGUS is a local-first job discovery, matching and application assistant. Everything
runs on your own machine: PostgreSQL, the API, the background worker and the LLM.
It costs nothing to run.

> Product rules and guardrails: [`../docs/`](../docs/).
> Learning guide for the LLM parts: [`../docs/learning/01-llm-fundamentals.md`](../docs/learning/01-llm-fundamentals.md).

## Status

| Milestone | State |
|---|---|
| M0 Backend foundation: API + Swagger, schema, task queue + worker, local LLM | done |
| M1 Resume upload → local LLM parse → review → import; profile sections; export/delete | done |
| M3 Explainable matching: synonyms + embedding similarity (pgvector HNSW), weights, hard filters, shortlist | done |
| React UI: dashboard, jobs + match explanations, profile/resume, preferences, companies, activity, LLM Lab | done |
| M2 Automatic discovery from Greenhouse / Lever / Ashby boards | next |

Tests: 125 backend (+2 live-model) and 5 frontend; every page is also checked in a headless browser.

## Requirements

| Tool | Why | Install |
|---|---|---|
| `uv` | Python + dependency manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Podman (or Docker) + compose | PostgreSQL 18 + pgvector container | preinstalled on Fedora |
| Ollama ≥ 0.40 | local LLM server (user service) | see "LLM" below |
| NVIDIA GPU (optional) | fast inference; CPU works, slowly | driver ≥ 550 |

## Quick start

```bash
cd argus
make env          # creates .env with a random database password (never committed)
make db-up        # PostgreSQL 18 + pgvector on 127.0.0.1:5433
make install      # backend dependencies
make migrate      # create tables / indexes
make api          # http://127.0.0.1:8000/docs  <- Swagger UI
make worker       # (2nd terminal) background worker
make web-install  # frontend dependencies (once)
make web          # (3rd terminal) UI at http://127.0.0.1:5173
make check-all    # backend + frontend quality gates
```

Run `make help` to list every command.

## LLM

```bash
systemctl --user status ollama     # Ollama runs as a user service on 127.0.0.1:11434
make llm-status                    # installed / loaded models + GPU memory
make llm-pull                      # gemma4:26b-a4b-it-qat (16 GB) + nomic-embed-text
make llm-create                    # build the tuned 'argus-extractor' variant
make test-llm                      # tests against the real model
```

Models are set in `.env` (`ARGUS_LLM_CHAT_MODEL`, `ARGUS_LLM_EMBED_MODEL`).

## Project layout

```
argus/
├── Makefile, compose.yaml, .env.example
├── llm/Modelfile.extractor          # tuned model variant (params + system prompt)
└── backend/
    ├── pyproject.toml               # deps (pinned ranges), ruff, mypy, pytest config
    ├── app/
    │   ├── main.py                  # app factory: middleware, Swagger, lifespan
    │   ├── api/                     # router aggregation (/api/v1) + dependencies
    │   ├── core/                    # config, logging (PII redaction), errors, middleware, OpenAPI
    │   ├── db/                      # psycopg2 pool, migration runner, SQL helpers
    │   │   └── migrations/*.sql     # numbered, immutable, checksummed
    │   ├── shared/                  # pagination (keyset), text normalization, schemas
    │   ├── modules/<feature>/       # one package per feature:
    │   │   ├── router.py            #   HTTP layer (validation, status codes, docs)
    │   │   ├── schemas.py           #   Pydantic request/response models
    │   │   ├── service.py           #   use-cases + transaction boundaries
    │   │   └── repository.py        #   raw parameterized SQL
    │   └── worker/                  # task-queue consumer + handlers
    └── tests/{unit,integration,llm}/
```

Feature modules: `health`, `profile` (+ sections), `resume`, `preferences`, `companies`, `jobs`,
`matching`, `llm`, `tasks`, `system`, `audit`.

```
frontend/                          # React 19 + TypeScript + Vite + Tailwind 4
├── src/api/schema.d.ts            # GENERATED from /openapi.json (make web-api) - never edit
├── src/api/client.ts              # typed fetch client + error envelope handling
├── src/api/queries.ts             # every server call as a TanStack Query hook
├── src/components/{layout,ui}/    # app shell + small design system (form, primitives, toast)
├── src/pages/                     # one file per screen (profile/ has its sub-components)
└── src/lib/                       # pure helpers (+ *.test.ts)
```

## Engineering conventions

- **Raw SQL, no ORM.** psycopg2 with parameters (`%(name)s`) only. Ruff rule S608 flags
  string-built SQL. Dynamic identifiers use `psycopg2.sql.Identifier`.
- **Every hot query has an index**, and `tests/integration/test_migrations_and_indexes.py`
  checks with `EXPLAIN` that each query actually uses it. Lists use **keyset pagination**
  (O(page size) at any depth), never OFFSET.
- **Never write an O(n²) algorithm.** Use dicts and sets for lookups, set-based SQL
  (`unnest`, `execute_values`) for batches, and `dict.fromkeys` for order-preserving de-duplication.
- **Short transactions.** Never hold a database connection during an LLM or network call.
- **Migrations are immutable.** Add a new numbered file instead of editing an applied one; the
  runner checks checksums.
- **Treat all external text as untrusted** (job posts, emails). The LLM has no tools; its output
  is schema-validated, and decisions are made in code.
- **Personal data never goes into logs or the audit trail.** The log formatter redacts
  emails, phone numbers, tokens and URL credentials.
- Quality gate: `make check` (ruff + mypy --strict + pytest).

## Security defaults

- **Local-only network:** the API, PostgreSQL and Ollama listen only on 127.0.0.1.
- **Request protection:** a `Host` allow-list blocks DNS rebinding, and an `Origin` check
  blocks cross-site writes (CSRF).
- **Secrets:** they live only in `.env` (git-ignored, mode 600) as `SecretStr`.
- **Kill switch:** `POST /api/v1/system/pause` stops the worker from taking new tasks.
