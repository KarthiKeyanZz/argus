# 06 — Prompting & structured output

The prompt is the main way to tell an LLM what to do. For applications like ARGUS, you also need
the answer in a **machine-readable shape** (JSON) that code can trust. This chapter covers both.

---

## Anatomy of a prompt

| Part | Purpose | ARGUS example |
|---|---|---|
| **System prompt** | Standing role, rules and constraints | "You are a precise information-extraction engine… never guess" |
| **User message** | The task + the input data | "Extract the facts from this posting: <<<POSTING … POSTING>>>" |
| **Examples (few-shot)** | Show the desired behaviour | A mini posting → the expected fields |
| **Output format** | The schema or format | JSON Schema sent as `format` |

---

## Prompting techniques that work

1. **Be explicit and specific.** "Use short lowercase skill names like 'python', 'rest api'" beats
   "list skills".
2. **Say what NOT to do.** "Degree subjects are not skills" fixed a real ARGUS bug.
3. **Give the model a place for everything.** If "computer science" has no slot, it will end up
   in the skills list. Adding `education_fields` fixed that. (See
   [projects/06](../projects/06-tuning-case-study.md), bug 3.)
4. **Few-shot examples.** 1–3 short examples teach format and edge cases better than paragraphs
   of rules.
5. **Delimit data.** Wrap input in unambiguous markers (`<<<POSTING … POSTING>>>`) so
   instructions and data can't blur together. This also defends against prompt injection
   ([12](12-safety-prompt-injection-privacy.md)).
6. **Allow "unknown".** Tell the model to use `null` / `"unknown"` instead of guessing.
7. **Don't ask for arithmetic.** Ask the model to *copy* numbers and dates; compute in code.
8. **Version your prompts.** Store `prompt_version` with every result so you know which prompt
   produced it (`JOB_EXTRACTION_VERSION = 2`).

### Chain-of-thought

Asking the model to reason step by step ("think before you answer") improves reasoning tasks,
at the cost of more tokens. Gemma 4's `think` option does this natively, with the reasoning
returned separately. For **extraction** it usually adds latency without improving accuracy
(measured in ARGUS: 23 s vs 5 s for the same facts).

---

## Structured output: three levels of strictness

| Level | How | Reliability |
|---|---|---|
| 1. "Please answer in JSON" | Instruction in the prompt | Sometimes adds prose or broken JSON |
| 2. JSON mode (`format: "json"`) | Engine forces syntactically valid JSON | Valid JSON, but any shape |
| 3. **JSON Schema** (`format: {schema}`) | Engine forces JSON **matching your schema** | Correct shape every time |

ARGUS uses level 3 everywhere.

---

## How constrained decoding works

The engine converts your JSON Schema into a **grammar** (llama.cpp uses a format called GBNF).
At every decode step, it checks which tokens could still lead to valid output and sets the
probability of all others to zero:

```
Schema says next must be:  "seniority": one of ["intern","entry","junior","mid","senior","lead","unknown"]
Model's top tokens:        "Senior" 0.41 · "senior" 0.38 · "Mid" 0.10 ...
After masking:             "senior" (valid prefix)  ← "Senior" is not allowed (case differs)
```

So the model **physically cannot** produce a field that isn't in the schema, a wrong type, or an
enum value outside the list.

### What schema features buy you

| Schema feature | Effect on generation | ARGUS use |
|---|---|---|
| `enum` | Only listed values | seniority, work_mode, employment_type |
| `type: integer/number` | Digits only | years of experience |
| `pattern` (regex) | String must match | dates: `^((Jan\|…\|Dec) )?[12][0-9]{3}$\|Present` |
| `maxItems` | Array closes after N items | stops runaway repetition loops |
| `required` | Key must be emitted | **all** keys required (see below) |
| `anyOf [type, null]` | Allows `null` | missing facts stay `null` instead of being invented |

### The "optional field" trap (a real ARGUS bug)

In Pydantic, a field with a default value becomes **optional** in its JSON Schema. A grammar built
from an optional property lets the model skip that key — and it did: the resume parser silently
returned no education or experience. Fix: `llm_schema()` marks **every** property as required;
`null` still expresses "absent".

---

## A schema guarantees shape, not truth

Constrained decoding guarantees the JSON *parses* and *fits the schema*. It does **not**
guarantee the content is correct. ARGUS therefore still:

1. validates with Pydantic (`model_validate_json`)
2. post-processes deterministically (lower-case, de-duplicate, drop non-skills)
3. shows results to you for review before anything is saved (resume import)
4. measures accuracy on test cases ([10 — Evaluation](10-evaluation.md))

---

## Field order matters

The model writes keys in schema order, and every token is conditioned on what it already wrote.
Order your schema to help it:

```
title → summary → education_level → education_fields → years → seniority → skills
           ↑ "understand first"        ↑ degree subjects get a slot before skills
```

Writing a summary first works like a mini chain-of-thought. Putting `education_fields` before
`required_skills` means "computer science" lands in the right place.

---

## Key takeaways

1. Clear rules, a place for everything, delimited data, few-shot examples, `null` allowed.
2. Use JSON Schema constrained decoding for anything code consumes.
3. Make every key required, cap arrays, add regex patterns, order fields deliberately.
4. Validate and post-process anyway: shape ≠ truth.

## In ARGUS

- Prompts (v2 + few-shot example): `app/modules/llm/prompts.py`
- Job schema with ordering notes: `JobFacts` in `app/modules/llm/schemas.py`
- Resume schema with date patterns: `app/modules/resume/schemas.py`
- `llm_schema()` (all keys required): `app/modules/llm/structured.py`
