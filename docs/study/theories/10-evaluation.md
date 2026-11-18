# 10 — Evaluation: measuring an LLM system honestly

> "If you can't measure it, you can't improve it." Most of the real work in LLM engineering is
> evaluation. Without it, every prompt change is a guess.

---

## Why LLM systems need special evaluation

- Outputs vary (sampling), so one good example proves nothing.
- A prompt change can fix one case and silently break five others.
- "Looks right" isn't measurable. You need **labelled test cases** and **metrics**.

---

## Building a test set

1. Collect **realistic inputs**: real job postings, a variety of resumes.
2. Write the **expected output** for each, by hand or by correcting model output.
3. Include **edge cases**: postings with no skills listed, ranges ("0–2 years"), "senior"
   roles, prompt-injection attempts, very long text, non-English text.
4. Keep it **fixed**: compare every model or prompt version on the same set.
5. Never train on it (if you later fine-tune).

Even **30–50 cases** reveal most problems.

---

## Metrics you'll use

### For extraction fields

| Metric | Question it answers | Example |
|---|---|---|
| **Exact match** | Is the field exactly right? | seniority == "junior" |
| **Precision** | Of the skills the model listed, how many are correct? | listed 10, 8 correct → 0.8 |
| **Recall** | Of the true skills, how many did it find? | 12 true, found 8 → 0.67 |
| **F1** | Balance of both | 2·P·R / (P+R) |
| **Validity rate** | How often is the output usable at all? | schema-valid, `done_reason == stop` |
| **Latency** | Seconds per item, tokens/s | 4–9 s per posting |

### For matching thresholds (classification)

|  | predicted "same" | predicted "different" |
|---|---|---|
| **actually same** | true positive (TP) | false negative (FN) |
| **actually different** | false positive (FP) | true negative (TN) |

- **Precision** = TP / (TP + FP): how trustworthy a "match" is
- **Recall** = TP / (TP + FN): how many true matches we catch

There is always a **trade-off**: raising the threshold improves precision and lowers recall.
Choose based on the cost of each error. For ARGUS, a false "you have this skill" could lead to
applying under false pretences, so **precision is prioritized**.

---

## Calibration: ARGUS's skill-similarity threshold

We didn't guess the 0.70 threshold. We measured it:

1. Wrote 14 pairs that mean the same skill and 16 that don't.
2. Embedded them and computed cosine similarity, with and without task prefixes.
3. Found the lowest threshold with **zero false positives**:

| Prefix | Threshold | Recall | Margin over the highest wrong pair |
|---|---|---|---|
| none | 0.749 | 10/14 | **0.135** |
| `clustering: ` | 0.853 | 10/14 | 0.022 |

4. Picked **no prefix, threshold 0.70**: same recall, much wider safety margin.

That's a miniature version of how every threshold in an ML system should be chosen.

---

## LLM-as-a-judge (use with care)

Using an LLM to grade another LLM's free-text output (e.g. "is this cover letter accurate and
professional?") scales evaluation, but judges have biases: they prefer longer answers, their own
style, and the first option shown. Mitigations: clear rubrics, pairwise comparison with swapped
order, and spot-checking against human labels.

For **extraction** prefer exact metrics; use judges only for open-ended text.

---

## Offline vs online evaluation

| Offline | Online |
|---|---|
| Fixed test set, before release | Real usage, after release |
| Repeatable, compares versions | Catches drift and new edge cases |
| ARGUS: `tests/llm/test_live_model.py` (tiny today), planned eval set in M4 | ARGUS: review queue + corrections you make in the UI become new test cases |

---

## A good evaluation loop

```
change prompt/model ──► run eval set ──► compare metrics with previous version
        ▲                                         │
        │                     better? ── yes ──► keep + record version
        │                                         │ no
        └────────────── investigate failures ◄────┘
```

## Key takeaways

1. Build a fixed, labelled test set with edge cases.
2. Measure precision/recall/validity/latency, not impressions.
3. Choose thresholds from data and from the cost of each error type.
4. Version prompts and models; compare on the same set every time.

## In ARGUS

- Unit tests with mocked LLM responses: `tests/unit/test_llm_service.py`
- Live-model tests (incl. injection resistance + reproducibility): `tests/llm/test_live_model.py`
- Threshold constants with calibration notes: `app/modules/matching/scoring.py`
- Planned eval harness: [projects/08](../projects/08-future-llm-work.md)
