# 07 — Embeddings & vector search

Chat models *generate* text. **Embedding models** *measure* text: they turn any text into a
fixed-length list of numbers (a **vector**) such that texts with similar meaning get vectors that
point in similar directions. This is what lets ARGUS see that "algorithm design" is close to
"data structures and algorithms" even though the words differ.

---

## From text to vector

```
"Entry-level Backend Developer (FastAPI)"  ──► nomic-embed-text ──► [0.021, -0.113, 0.067, ... ]  (768 numbers)
"junior python backend developer"          ──►                  ──► [0.018, -0.097, 0.071, ... ]
```

Each dimension isn't individually meaningful. *Directions* in the 768-dimensional space encode
meaning: topics, roles, technologies, seniority…

### How embedding models are trained (contrastive learning)

They're trained on pairs that *should* be close (a question and its answer, a title and its
abstract) and pairs that *shouldn't*. The objective pulls related pairs together and pushes
unrelated ones apart. Some models, like nomic-embed-text, recommend **task prefixes**
(`search_query: `, `search_document: `, `clustering: `) because they were trained with them.
ARGUS measured both options and found **no prefix** worked best for short skill strings
([projects/05](../projects/05-matching-engine.md)).

---

## Measuring closeness: cosine similarity

```
cos(a, b) = (a · b) / (|a| × |b|)
           = Σ aᵢbᵢ / ( √Σaᵢ² × √Σbᵢ² )
```

- **1** → same direction (same meaning)
- **~0** → unrelated
- negative → opposite (rare in practice for text)

It ignores vector *length* and only compares *direction*. Cost: O(d) for d dimensions.

A real result from your machine (query: "junior python backend developer"):

| Candidate | Cosine |
|---|---|
| Entry-level Backend Developer (FastAPI) | 0.689 |
| Graduate Software Engineer – Python/Django | 0.637 |
| Senior Staff Machine Learning Engineer | 0.495 |
| Restaurant Manager | 0.417 |

Note that "FastAPI" ranked first although the query never mentions it. The model "knows" that
FastAPI is a Python backend framework.

---

## ⚠ Similarity ≠ equivalence

Embeddings capture **relatedness**. Related but different things can score high:

| Pair | Score (`clustering:` prefix) | Same skill? |
|---|---|---|
| java ~ javascript | 0.831 | ❌ |
| c++ ~ c | 0.822 | ❌ |
| containers ~ docker | 0.796 | ✅ |

A true synonym can score *lower* than a false one. So you can't trust a single similarity number
blindly. You must **calibrate a threshold on real labelled pairs** and expect some errors. That
is what ARGUS did ([10 — Evaluation](10-evaluation.md)), ending up with three bands:
**similar** (≥ 0.70, earns credit), **related** (0.60–0.70, shown only), **missing**.

---

## Finding the nearest vectors fast

Comparing a query with every stored vector is O(n × d), which is fine for 100 vectors but slow
for millions. **Approximate Nearest Neighbour (ANN)** indexes trade a little accuracy for huge
speed-ups.

### HNSW — Hierarchical Navigable Small World

```
layer 2:   A ─────────────── K                    (few nodes, long jumps)
layer 1:   A ──── D ──── K ──── P                  (more nodes)
layer 0:   A─B─C─D─E─F─G─H─I─J─K─L─M─N─O─P        (all nodes, short links)
```

Search starts at the top layer, greedily moves to the neighbour closest to the query, then drops
a layer and repeats. That's roughly **O(log n)** hops instead of n comparisons. It's
*approximate*: it can occasionally miss the true nearest neighbour. Tuning knobs (pgvector):
`m` (links per node), `ef_construction` (build quality), `ef_search` (search breadth vs speed).

### pgvector — vectors inside PostgreSQL

ARGUS stores vectors in PostgreSQL with the **pgvector** extension:

```sql
CREATE INDEX skill_embedding_hnsw ON skill USING hnsw (embedding vector_cosine_ops);

-- nearest profile skill to a job skill (<=> is cosine DISTANCE = 1 - similarity)
SELECT normalized_name, 1 - (embedding <=> $1) AS similarity
FROM skill
ORDER BY embedding <=> $1
LIMIT 1;
```

Keeping vectors next to the rest of the data means one database, transactions, joins, and no
separate vector DB to run.

---

## Typical uses of embeddings

| Use | How | ARGUS |
|---|---|---|
| Semantic search | Embed query + documents, return nearest | LLM Lab similarity tool |
| Fuzzy matching | Nearest neighbour above a threshold | job skill ↔ profile skill |
| Similar-item lookup | Nearest items to an item | job title ↔ target titles |
| Retrieval for RAG | Find relevant chunks to put in the prompt | planned: question ↔ answer library |
| Clustering / dedupe | Group close vectors | planned: duplicate job detection |

---

## Caching embeddings

Embedding the same text twice gives the same vector, so **cache it**. ARGUS's `skill_embedding`
table maps *text → vector*. Each distinct skill or title is embedded once, ever; the second
scoring run made **zero** embedding calls (verified in a test).

If you change the embedding model, every vector must be recomputed: vectors from different
models are not comparable. The cache stores the model name for that reason.

---

## Key takeaways

1. Embedding = text → vector; closeness in direction = closeness in meaning.
2. Cosine similarity compares directions; it measures *relatedness*, so calibrate thresholds.
3. ANN indexes (HNSW) make nearest-neighbour search ~O(log n).
4. Cache embeddings; never mix vectors from different models.

## In ARGUS

- Embedding calls + cosine: `app/modules/llm/service.py` (`embed`, `similarity`, `cosine`)
- Cache + HNSW lookups: `app/modules/matching/repository.py`
- Vector columns and indexes: `app/db/migrations/0003_matching_and_aliases.sql`
