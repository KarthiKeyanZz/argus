# 06 — Tuning case study: six real bugs and how they were fixed

Each bug below happened on your machine with real data. Together they're a compact course in
practical LLM engineering. Notice that **none** needed retraining: all were fixed with
parameters, prompts, schemas or code.

---

## Bug 1 — 24,000 characters of looping JSON

**Symptom.** Resume parse returned huge unterminated JSON; `done_reason: "length"` after 7,800
tokens.

**What the model wrote:**

```json
"experience": [{ "company": "Example Labs", "title": "Backend Developer Intern",
                 "months": -6000000000000000 },
               { "company": "Example Labs", "title": "Backend Developer Intern",
                 "months": -6000000000000000 },   ... repeated hundreds of times
```

**Root cause.**
1. The schema asked for `months` (an integer), i.e. asked the model to **compute** "Jun–Aug
   2025 → 3". LLMs don't calculate; it produced a nonsense number.
2. At `temperature: 0` (greedy), once a pattern starts, repeating it is the most likely
   continuation → **degenerate repetition loop**.

**Fix.** Ask for dates as written (`start`, `end`) and compute months in code; add `maxItems`
to every list (the grammar then *cannot* emit more items); cap `num_predict`; reject
`done_reason == "length"` instead of saving garbage.

**Theory:** [05 — Sampling](../theories/05-sampling-and-decoding.md),
[06 — Structured output](../theories/06-prompting-and-structured-output.md).

---

## Bug 2 — commentary inside a date field

**Symptom.** `"end": "Aug 2025, 2025 (implied by context/dates provided: …)"`

**Root cause.** A free-text string field lets the model "explain itself".

**Fix.** Regex `pattern` on date fields: only `Jun 2025`, `2025` or `Present` are possible.
Result: `start 'Jun 2025'  end 'Aug 2025'`.

---

## Bug 3 — degree subjects listed as skills

**Symptom.** Cloudflare's internship: required skills = `computer science, engineering,
mathematics, statistics` → 0 matches.

**Root cause.** The schema had no place for degree subjects, so they leaked into the nearest
list.

**Fix (prompt v2).**
- New `education_fields` slot, placed **before** the skill lists (field order steers
  generation).
- A clear definition of "skill" plus a NOT-skills list.
- A one-shot example.
- A code-level stop-list (`NON_SKILLS`) as a deterministic safety net.

Result: `edu=['computer science', 'engineering', 'mathematics', 'statistics']` and skills clean.

---

## Bug 4 — resume parse silently dropped education and experience

**Symptom.** Parse succeeded, but `education: []` and `experience: []`.

**Root cause.** Pydantic marks fields with defaults as **optional** in JSON Schema. The grammar
let the model skip optional keys, and it did.

**Fix.** `llm_schema()` sets `required` = all properties, recursively. `null` still expresses
"absent". A unit test locks it in.

---

## Bug 5 — synonyms not matched

**Symptom.** "rest apis" ≠ "rest api"; "data structures" ≠ "data structures and algorithms".

**Fix.** ~40 new aliases (migration 0003), plus semantic matching with a **calibrated**
threshold ([05 — Matching engine](05-matching-engine.md)).

---

## Bug 6 — extraction took 23 s instead of 5 s

**Symptom.** Worker extractions were 4× slower than the same call from Swagger.

**Root cause.** Gemma 4 **thinks by default**; the worker didn't pass `think: false`.

**Fix.** `think=false` default for extraction. The thinking output didn't change the facts, so
it was pure latency.

---

## Bonus bugs found by testing (not LLM-specific)

| Bug | Found by | Fix |
|---|---|---|
| Readiness said `nomic-embed-text` not installed | live smoke test | Ollama names it `…:latest`; normalize tags |
| LinkedIn imported as `linkedin.com/in/x` → form validation would fail | UI screenshot review | `with_scheme()` adds `https://`, rejects `javascript:` etc. |
| Form labels not linked to inputs (accessibility) | headless browser test | `Field` passes ids via React context + component test |
| A LISTEN/NOTIFY test was flaky | repeated test runs | wait on the socket like the real worker does |

---

## The general lessons

1. **Don't ask LLMs to compute.** Copy, then calculate in code.
2. **Constrain everything**: enums, patterns, `maxItems`, all keys required, `num_predict`.
3. **Give every kind of information a slot**, and order slots deliberately.
4. **Back prompts with deterministic code** (stop-lists, normalization, validation).
5. **Measure** (calibration, benchmarks, tests), then decide.
6. **Test the real thing**: half of these bugs only appeared with the real model, the real UI
   or real data.
