# ARGUS — Implementation plan and decision log

This file records decisions made with the project owner. Where it conflicts with the
original requirements documents, **this file wins**.

## Decisions (2026-11-13)

| # | Decision | Overrides |
|---|---|---|
| D1 | **Automated application submission is the core goal.** The user approves *policy* (profile, answer library, thresholds, caps, allowed sources) once; no per-application approval. | Guardrails §7 "assisted mode default" / "no autonomous mode in first milestone" |
| D2 | Autonomous mode keeps the guardrail limits: daily/weekly caps, per-company cooldown, fit threshold, hard filters, stop on unknown required questions ("needs answer" queue), dry-run → fill-only → live rollout. | — |
| D3 | CAPTCHA is never solved or evaded: pause + desktop notification for the user. No LinkedIn / Naukri / Indeed automation (ToS, account bans); they can only be added manually. | — |
| D4 | OTP: automatic extraction from Gmail (read-only OAuth) for verification flows ARGUS itself started; codes kept only in memory, at most 10 minutes. | Guardrails §8 "display code and ask user approval" |
| D5 | UI: React + TypeScript (Vite). All inputs (profile, preferences, locations, companies) are entered in the UI. | — |
| D6 | Database: PostgreSQL 18 (+ pgvector) with **psycopg2 and raw SQL**, no ORM. Migrations: numbered `.sql` files and a small checksummed runner. | Core prompt "SQLite acceptable" |
| D7 | Swagger / OpenAPI is required (`/docs`, `/redoc`, `/openapi.json`). | — |
| D8 | LLM: local Ollama, chat model **`gemma4:26b-a4b-it-qat`** (Apache 2.0), embeddings **`nomic-embed-text`**. No paid or cloud LLM for personal data. Model is configurable. | — |
| D9 | No O(n²) code; indexed, keyset-paginated queries. | — |
| D10 | The owner is learning AI/LLMs: code and `docs/learning/` explain the LLM mechanics. | — |

## Milestones

| # | Milestone | Status |
|---|---|---|
| M0 | Backend foundation: API + Swagger, schema, task queue + worker, LLM integration, tests | **done** |
| M1 | Profile & preferences in UI: resume upload and parsing, fact verification, export/delete (answer library pending) | **done** |
| M2 | Discovery: Greenhouse / Lever / Ashby adapters, form-schema fetch, dedupe, closed-job detection | **next** |
| M3 | Matching: rules + embeddings, hard filters, weights, explanations | **done** |
| M4 | LLM evaluation set + model comparison; tuned extraction | |
| M5 | Application prep: field resolution, tailored resume (selection, not generation), cover letters | |
| M6 | Apply runner (Playwright): mock forms → fill-only → live behind policy + caps; CAPTCHA pause | |
| M7 | Gmail: status classification, confirmations, automatic OTP | |
| M8 | Scheduling, React dashboard polish, retention, security tests | |

React frontend: done for M0/M1/M3 screens (dashboard, jobs, profile, preferences, companies, activity, LLM Lab).
