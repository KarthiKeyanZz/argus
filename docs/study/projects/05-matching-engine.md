# 05 — Matching engine deep-dive

The matching engine answers: **"How well does this job fit me, and why?"** It combines
deterministic rules, synonyms, embeddings and your preferences into an explainable 0–100 score.

> A score is a **ranking aid**, not a probability of being hired. Hard-filter failures are shown
> separately and never hidden behind a high score.

---

## Layer 1 — Canonical names (synonyms)

Before anything is compared, skill names are normalized and mapped through the `skill_alias`
table:

```
"JS" → normalize → "js" → alias → "javascript"
"Postgres database" → "postgres database" → "postgresql"
"OOPS" → "oops" → "object oriented programming"
```

~95 aliases (migrations 0002 + 0003). Exact, instant and free; covers the common cases before
any AI is involved.

## Layer 2 — Exact match

A job skill whose canonical name exists in your profile → **exact** (full credit).

## Layer 3 — Semantic match (embeddings)

For the remaining skills, ARGUS finds your **nearest profile skill** by cosine similarity using
pgvector's HNSW index:

```sql
SELECT p.normalized_name, 1 - (p.embedding <=> e.embedding) AS similarity
FROM skill p WHERE p.embedding IS NOT NULL
ORDER BY p.embedding <=> e.embedding
LIMIT 1;                        -- O(log n) via skill_embedding_hnsw
```

The similarity is then banded:

| Band | Similarity | Credit | Example |
|---|---|---|---|
| exact | (name match) | 1.0 | python ↔ python |
| **similar** | ≥ 0.70 | = similarity (e.g. 0.92) | algorithm design ↔ data structures and algorithms |
| **related** | 0.60–0.70 | 0 (shown only) | c++ ↔ c (0.61) · api design ↔ rest api (0.68) |
| missing | < 0.60 | 0 | go ↔ python |

### How the thresholds were chosen (calibration)

30 labelled pairs (14 same, 16 different), embedded with nomic-embed-text:

| Variant | Lowest zero-false-positive threshold | Recall | Margin |
|---|---|---|---|
| no prefix | 0.749 | 10/14 | 0.135 above the highest wrong pair (0.614) |
| `clustering:` prefix | 0.853 | 10/14 | 0.022 |

→ no prefix, **0.70** for "similar", **0.60** for "related". Precision first: a false "you have
this skill" is worse than a missed synonym.

## Layer 4 — Components and weights

| Component | How it's computed | Default weight |
|---|---|---|
| title | best cosine(job title, your target titles), mapped [0.45, 0.75] → [0, 1] | 25% |
| required_skills | Σ credit / number of required skills | 30% |
| preferred_skills | same for nice-to-haves | 10% |
| experience | min years ≤ your max → 1; above → 0; unstated: fresher-friendly 1, senior 0.2, else 0.7 | 20% |
| location | work-mode match + location match (remote always matches) | 10% |
| freshness | 1.0 for ≤ 7 days, linear to 0.2 at 60 days | 5% |

- **Unknown ≠ bad**: if a posting lists no skills or no title similarity exists, that component
  is **0.5 (neutral)** and flagged as unknown.
- Weights come from **Preferences** and are normalized to sum to 1.

```
score = 100 × Σ(component × weight) / Σ(weights)
```

## Layer 5 — Hard filters

Evaluated separately; any failure sets `passed_hard_filters = false` with a reason:

- requires more years than your max (default max 2)
- not fresher-friendly (if you require it)
- work mode not in your list
- location not in your list (if enforced)
- excluded company (normalized: "Evil Corp Ltd" = "EVIL CORP")
- excluded title keyword, matched as a **whole word** ("senior" ≠ "seniority")

---

## Real example (live run)

```
82  Software Engineering Intern (2027) @ Databricks  [PASS]
    title 0.90 · required 0.80 · experience 1.0 (fresher-friendly) · location 0.5 (unstated)
    exact:   python, java, data structures and algorithms, object oriented programming
    related: c++ ≈ c (0.61)  → no credit
40  Senior Backend Software Engineer @ Databricks   [FAIL]
    requires 5+ years (your max: 2); title contains excluded keyword 'senior'
```

---

## Complexity

| Step | Cost |
|---|---|
| Embeddings | each distinct text embedded once (cache), batches of 128 |
| Skill lookup | O(k · log P) per job: k job skills, P profile skills (HNSW) |
| Scoring | O(k + L + K) per job (skills, locations, keywords) |
| Batches | keyset pagination, 100 jobs per batch → O(N) overall |

No pairwise loops between jobs, or between all job skills and all profile skills.

## Files

- `app/modules/matching/scoring.py`: pure functions, thresholds, calibration notes
- `app/modules/matching/service.py`: orchestration, embedding cache, batches
- `app/modules/matching/repository.py`: SQL (HNSW lookups, upserts, shortlist)
- `tests/unit/test_scoring_and_resume_helpers.py`, `tests/integration/test_resume_and_matching.py`
