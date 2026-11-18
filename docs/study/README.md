# Study guide — AI, LLMs and how ARGUS uses them

This folder is your personal textbook for the project. It has two parts:

| Folder | What's inside | Read it when |
|---|---|---|
| [`theories/`](theories/) | General concepts: what an LLM is, how it works inside, inference, sampling, prompting, embeddings, tuning and fine-tuning, evaluation, agents, safety | You want to understand *why* things work |
| [`projects/`](projects/) | How those concepts are applied in ARGUS, with file paths, diagrams, real measurements from your machine, and hands-on labs | You want to see the theory in real code and try it |

Every theory file ends with **"In ARGUS"** pointers, and every project file points back to the
theory it uses, so you can jump between the two.

---

## Suggested reading paths

### Path A — "I'm new to LLMs" (≈ 4–5 hours)

1. [theories/01 — What is an LLM?](theories/01-what-is-an-llm.md)
2. [theories/02 — How an LLM works inside](theories/02-how-llms-work.md)
3. [projects/01 — ARGUS overview](projects/01-argus-overview.md)
4. [projects/02 — Why ARGUS uses an LLM, and where it doesn't](projects/02-why-and-where-llms-in-argus.md)
5. [theories/04 — Inference](theories/04-inference.md)
6. [theories/05 — Sampling & decoding](theories/05-sampling-and-decoding.md)
7. [projects/07 — Hands-on labs](projects/07-hands-on-labs.md) (labs 1–4)

### Path B — "I want to build with LLMs" (after Path A)

1. [theories/06 — Prompting & structured output](theories/06-prompting-and-structured-output.md)
2. [theories/07 — Embeddings & vector search](theories/07-embeddings-and-vector-search.md)
3. [projects/03 — The LLM workflows in ARGUS](projects/03-llm-workflows-in-argus.md)
4. [projects/05 — Matching engine deep-dive](projects/05-matching-engine.md)
5. [theories/10 — Evaluation](theories/10-evaluation.md)
6. [projects/06 — Tuning case study (real bugs)](projects/06-tuning-case-study.md)

### Path C — "I want to modify and train models"

1. [theories/03 — How models are trained](theories/03-how-llms-are-trained.md)
2. [theories/09 — Tuning & modifying models](theories/09-tuning-and-modifying-models.md)
3. [projects/04 — The inference stack on your machine](projects/04-inference-stack-on-your-machine.md)
4. [projects/08 — Future LLM work & fine-tuning plan](projects/08-future-llm-work.md)

---

## Full index

### theories/

| # | Topic |
|---|---|
| 01 | [What is an LLM?](theories/01-what-is-an-llm.md) |
| 02 | [How an LLM works inside — tokens, embeddings, attention, transformer](theories/02-how-llms-work.md) |
| 03 | [How LLMs are trained — pretraining, instruction tuning, preference tuning](theories/03-how-llms-are-trained.md) |
| 04 | [Inference — prefill, decode, KV cache, memory, quantization, MoE, speed](theories/04-inference.md) |
| 05 | [Sampling & decoding — temperature, top-k, top-p, min-p, seeds, penalties](theories/05-sampling-and-decoding.md) |
| 06 | [Prompting & structured output — system prompts, few-shot, JSON Schema, grammars](theories/06-prompting-and-structured-output.md) |
| 07 | [Embeddings & vector search — cosine similarity, HNSW, pgvector](theories/07-embeddings-and-vector-search.md) |
| 08 | [RAG, grounding & hallucination](theories/08-rag-grounding-hallucination.md) |
| 09 | [Tuning & modifying models — parameters, Modelfiles, LoRA/QLoRA, distillation, merging](theories/09-tuning-and-modifying-models.md) |
| 10 | [Evaluation — measuring an LLM system honestly](theories/10-evaluation.md) |
| 11 | [Agents & tool use](theories/11-agents-and-tool-use.md) |
| 12 | [Safety, prompt injection & privacy](theories/12-safety-prompt-injection-privacy.md) |
| 13 | [Glossary](theories/13-glossary.md) |

### projects/

| # | Topic |
|---|---|
| 01 | [ARGUS overview — goal, architecture, data flow](projects/01-argus-overview.md) |
| 02 | [Why ARGUS uses an LLM, and where it deliberately doesn't](projects/02-why-and-where-llms-in-argus.md) |
| 03 | [The LLM workflows in ARGUS, step by step](projects/03-llm-workflows-in-argus.md) |
| 04 | [The inference stack on your machine — Ollama, Gemma 4, GPU, benchmarks](projects/04-inference-stack-on-your-machine.md) |
| 05 | [Matching engine deep-dive — synonyms, embeddings, scoring](projects/05-matching-engine.md) |
| 06 | [Tuning case study — six real bugs and how they were fixed](projects/06-tuning-case-study.md) |
| 07 | [Hands-on labs](projects/07-hands-on-labs.md) |
| 08 | [Future LLM work & a fine-tuning plan](projects/08-future-llm-work.md) |
| 09 | [Roadmap — what is built and what remains](projects/09-roadmap-and-remaining-work.md) |

> Related: [`docs/learning/01-llm-fundamentals.md`](../learning/01-llm-fundamentals.md) is the
> short quick-reference written during the build; this folder is the full course.
