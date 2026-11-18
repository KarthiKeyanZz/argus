# 08 — Future LLM work & a fine-tuning plan

This is the LLM-specific part of the roadmap. Each item says what the model will do, which
technique it uses, and what you'll learn from building it.

---

## 1. Evaluation harness (milestone M4) — *learn: evaluation*

Before changing models or prompts again, build the measuring stick.

```
eval/
  jobs/*.txt          30–50 real postings (varied: interns, seniors, no-skills, injection)
  jobs/*.expected.json hand-checked JobFacts
  resumes/*.docx      a few fictional resumes + expected ResumeFacts
run:  make eval MODEL=gemma4:26b-a4b-it-qat
out:  per-field exact match, skill precision/recall/F1, validity rate, p50/p95 latency
```

Compare `gemma4:26b-a4b-it-qat` vs `gemma4:12b` vs `qwen3:14b`, prompt v2 vs v3, `think`
on/off. Keep a results table in `docs/learning`.

## 2. Answer library + RAG for application questions (M5) — *learn: RAG, retrieval*

```
form question ──embed──► HNSW search on answer_library ──► top-5 approved answers
             ──► LLM: "choose an id or NONE"   (enum of ids = constrained choice)
             ──► NONE → "Needs answer" queue → you answer once → stored + embedded
```

- Model never writes free text for factual questions (no invented sponsorship status, salary…).
- Measure: how often the right id is chosen (top-1 accuracy) on a labelled question set.

## 3. Form-field resolution (M5/M6) — *learn: classification with constrained choices*

Map each form field label ("Current CTC", "Notice period (days)", "LinkedIn profile") to a
profile field or an answer id. Standard fields are handled by rules first; the LLM handles the
long tail; confidence below a threshold → ask you.

## 4. Cover letters and free-text answers (M5) — *learn: grounded generation + verification*

1. Retrieve verified facts relevant to the job (skills overlap, best achievement bullets).
2. Generate with temperature ~0.7 from **only** those facts.
3. **Verification pass**: a second constrained call extracts every claim from the draft;
   code checks each claim against your facts; unsupported claims → reject or regenerate.

## 5. Email classification and OTP (M7) — *learn: small classifiers, untrusted input*

- Classify job emails (interview / rejection / assessment / confirmation / other) with an enum
  schema; suggest status changes for you to accept.
- OTP: regular expressions first (deterministic), with the LLM only as a fallback for odd
  formats. Codes stay in memory ≤ 10 minutes and never reach logs or the database.

## 6. Fine-tuning project: distil a fast extractor — *learn: LoRA/QLoRA*

**Why:** Gemma 26B takes ~5 s per posting. Discovery may bring hundreds of postings a day. A
fine-tuned 1–4B model could be several times faster at similar accuracy *for this one task*.

**Plan:**

| Step | Detail |
|---|---|
| 1. Data | Let Gemma 26B extract 2,000+ postings (teacher). Hand-correct ~200. |
| 2. Split | 80 / 10 / 10; the hand-corrected eval set from item 1 stays as the test set |
| 3. Base | A small instruct model with a permissive licence that fits QLoRA on 12 GB |
| 4. Train | QLoRA (4-bit base + LoRA rank 16–32), 2–3 epochs, with Unsloth or HF TRL |
| 5. Compare | Same eval harness: F1 on skills, exact match on years/seniority, latency |
| 6. Ship | Convert to GGUF → Modelfile with `FROM` + `ADAPTER` (or merged weights) → `ollama create argus-extractor-small` |
| 7. Route | Use the small model by default; fall back to 26B when validation fails |

**What you'll learn:** dataset building, train/validation curves, overfitting, quantization of
your own model, and the real trade-off between speed and accuracy.

Theory: [09 — Tuning & modifying models](../theories/09-tuning-and-modifying-models.md).

## 7. Apply runner assistance (M6) — *learn: bounded agents*

Playwright reads the page; the LLM only maps fields to approved values (constrained choice);
code fills, checks, screenshots, and stops on CAPTCHA, OTP or anything unexpected. See
[theories/11](../theories/11-agents-and-tool-use.md).

---

## Learning roadmap summary

| Order | Item | Main concept |
|---|---|---|
| 1 | Eval harness | Measurement, precision/recall |
| 2 | Answer library RAG | Retrieval + constrained selection |
| 3 | Form-field mapping | Classification, confidence thresholds |
| 4 | Cover letters | Grounded generation + verification |
| 5 | Email classification / OTP | Untrusted input, regex vs LLM |
| 6 | Distilled extractor | LoRA/QLoRA fine-tuning |
| 7 | Apply runner | Bounded agents, safety |
