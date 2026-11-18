# 02 — Why ARGUS uses an LLM, and where it deliberately doesn't

## The problem LLMs solve here

Job postings and resumes are **unstructured human text**, and every one is written differently:

```
"0-2 yrs exp; Python/Django a must; K8s is a plus; freshers welcome!!"
"Requirements: BS in CS, 3+ years with Java or Kotlin. Bonus: Kubernetes."
"We'd love someone comfortable with Postgres and REST services (new grads OK)."
```

Turning that into reliable fields (`min_years`, `required_skills`, `entry_level_friendly`) with
rules or regular expressions would need thousands of fragile patterns. An LLM understands all
three phrasings out of the box. **That's the core reason ARGUS uses one: language
understanding at scale.**

The second reason is **meaning comparison**. "algorithm design" vs "data structures and
algorithms", or "Backend Developer" vs "Software Engineer". Exact string matching fails;
**embeddings** capture that they're related.

---

## Where the LLM is used

| Task | Model | Why an LLM | Output |
|---|---|---|---|
| Read a job posting | Gemma 4 26B | Messy text → facts | `JobFacts` JSON (schema-constrained) |
| Read your resume | Gemma 4 26B | Any layout/wording → facts | `ResumeFacts` JSON draft for your review |
| Compare skills | nomic-embed-text | Synonyms and near-synonyms | vectors → cosine similarity |
| Compare titles | nomic-embed-text | Role similarity | best similarity to your target titles |
| LLM Lab | both | Learning and experiments | text + metrics |
| *Planned:* answer form questions | Gemma | Map a question → approved answer | an id from a list (RAG) |
| *Planned:* classify emails | Gemma | "interview / rejection / assessment…" | enum |
| *Planned:* draft cover letters | Gemma | Writing from verified facts | text, verified against facts |

---

## Where the LLM is deliberately **not** used

| Task | Done by | Why not the LLM |
|---|---|---|
| Arithmetic (months of experience, totals) | Python (`resume/dates.py`) | LLMs are bad at maths (it produced `-6000000000000000`) |
| Scoring and ranking | Pure Python (`matching/scoring.py`) | Must be explainable, reproducible, and testable |
| Hard filters (years, keywords, companies) | Python | A rule must never be "probably" applied |
| Synonyms (js → javascript) | SQL table `skill_alias` | Exact, instant, free, editable |
| Deciding to apply / submit | Code + your policy (planned) | Consequential actions need deterministic checks |
| Duplicate detection, URL cleaning | Python | Deterministic tasks |
| Security, validation, permissions | Code | Can't be left to a model that can be prompt-injected |

**Design principle:** *use the LLM for understanding language; use code for decisions, maths
and rules.* The LLM's output is always **data that code checks**, never an instruction that code
obeys.

---

## Why a local model (Gemma 4 26B via Ollama)?

| Requirement | How the choice meets it |
|---|---|
| Free | Open weights (Apache 2.0 per Ollama's library), runs on your GPU |
| Private | Resume and personal data never leave your machine |
| Good enough quality | 26B-parameter MoE: strong extraction quality in tests |
| Fast enough | MoE ~4B active per token → ~60 tokens/s; extraction ~4–9 s |
| Structured output | Ollama supports JSON-Schema-constrained decoding |
| Learnable | You can inspect, tune, and later fine-tune |

Alternatives considered: `gemma4:12b` (faster, fits fully in VRAM — the fallback), `qwen3:14b`
(strong extractor), cloud APIs (rejected: cost + privacy).

---

## The LLM's job description, in one paragraph

> The model reads untrusted text and fills a fixed form. It may write only what the form allows,
> must write `null` when the text doesn't say, never computes, never decides, and never acts.
> Everything it writes is validated, normalized, and either shown to you for review or fed into
> deterministic, explainable code.

Related theory: [theories/06](../theories/06-prompting-and-structured-output.md),
[theories/08](../theories/08-rag-grounding-hallucination.md),
[theories/11](../theories/11-agents-and-tool-use.md).
