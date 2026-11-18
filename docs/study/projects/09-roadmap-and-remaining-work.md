# 09 — Roadmap: what is built and what remains

Status as of 2026-11-14.

## ✅ Built

| Area | What works |
|---|---|
| Backend foundation | FastAPI + Swagger, PostgreSQL 18 + pgvector, raw-SQL repositories, migrations with checksums, connection pool, task queue (LISTEN/NOTIFY, SKIP LOCKED, retries), audit trail, global pause, PII-redacting logs, Host/Origin protection |
| Local LLM | Ollama user service, Gemma 4 26B (QAT) + nomic-embed-text, playground endpoints, Modelfile variant |
| Job extraction | Prompt v2, JSON-Schema constrained, injection-tested, worker task |
| Resume (M1) | Safe PDF/DOCX upload, local LLM parse → review → import, profile sections CRUD, export + delete all |
| Matching (M3) | Synonyms, embeddings + HNSW, calibrated thresholds, weights, hard filters, shortlist, auto re-score |
| Frontend | Dashboard, Jobs (+ manual add), Job detail with score explanation, Profile + resume review, Preferences, Companies, Activity, LLM Lab |
| Quality | 125 backend tests + 2 live-model tests, 5 frontend tests, strict mypy, ruff, eslint, browser checks |
| Learning | `docs/learning/01`, this `study/` course |

---

## ⏳ Remaining — product milestones

| # | Milestone | Main pieces |
|---|---|---|
| **M2** | **Automatic job discovery** (next) | Greenhouse / Lever / Ashby board adapters; aggregator APIs (Adzuna with a free key, Remotive); starter company list; self-growing company registry; scheduled crawling; closed-job detection; HTML sanitization; outbound HTTP client with host allow-list, per-host rate limits, `Retry-After` |
| M4 | LLM evaluation harness | Labelled sets, metrics, model/prompt comparison |
| M5 | Application preparation | Answer library API + UI, RAG answer selection, form-field resolution, tailored resume (selection of verified bullets → PDF/DOCX), cover letters with verification, "Needs answer" queue, auto-apply policy (caps, cooldowns, thresholds) |
| M6 | Apply runner | Playwright; mock forms → fill-only → live; CAPTCHA pause + desktop notification; screenshots + confirmation evidence; idempotency; application tracker states |
| M7 | Gmail | OAuth (read-only), narrow queries, status classification, confirmation detection, automatic OTP (memory-only) |
| M8 | Scheduling & hardening | Discovery schedule, retention policies, security tests, docs |

## ⏳ Remaining — known gaps and technical debt

| Gap | Notes |
|---|---|
| Application tracker API + UI | `application` / `application_event` tables exist; no endpoints or screens yet |
| Answer library API + UI | Table + vector index exist; nothing uses them yet |
| Certifications in the UI | API exists; no card on the Profile page |
| Settings page | Model choice, API keys (Adzuna, Gmail), schedule, data retention |
| Secrets in the OS keyring | Needed before storing API keys / OAuth tokens |
| Outbound HTTP client | Planned in M0, not built; required for M2 |
| One-command start | e.g. `make up` / systemd units for API + worker; serve the built UI from FastAPI |
| Frontend E2E tests in the repo | Browser checks were run ad hoc; add a Playwright suite |
| Code splitting | Single 443 KB JS bundle; lazy-load pages |
| Dark-mode and mobile polish | Styles exist; not visually reviewed |
| Git history | Repo initialized, **nothing committed yet** |
| Guardrail docs | Original docs still describe assisted mode; the decision log overrides them |
| Test data | The fictional "Alex Example" and 8 sample jobs are still in the database |

## ❓ Decisions needed from you

1. **Target countries / cities**: decides which sources to integrate and the starter company list.
2. **Adzuna API key** (free, ~2 minutes): biggest coverage for India.
3. Whether to **commit** the current work to git (and whether to create a private GitHub repo).
