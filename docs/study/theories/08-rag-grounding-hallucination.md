# 08 — RAG, grounding & hallucination

## Hallucination

A **hallucination** is fluent, confident output that is false or unsupported. It isn't a bug in
one model; it follows from how LLMs work:

1. They are trained to produce **plausible** continuations, not verified facts.
2. Preference tuning rewards **helpful-looking** answers, so filling a gap can look better than
   "I don't know".
3. They have no access to facts that aren't in their weights or their prompt.

Examples relevant to ARGUS:
- Claiming you know Kubernetes because a job requires it (fabricated qualification).
- Inventing "3 years of experience" when the posting says nothing.
- Computing internship months wrongly (we saw `-6000000000000000`).

For ARGUS a hallucination isn't just a quality issue. It would mean **misrepresenting you to an
employer**, which the guardrails forbid.

---

## Grounding

**Grounding** means making the model answer *from provided evidence* instead of from memory,
and checking that it did.

Techniques, from weakest to strongest:

| Technique | Example |
|---|---|
| Instruction | "Only extract what the posting states; use null otherwise." |
| Put the evidence in the prompt | Paste the actual posting / resume text (fenced) |
| Allow "unknown" in the schema | `min_years_experience: number \| null` |
| Ask for citations / provenance | Each answer field references the profile fact it came from |
| **Verify in code** | Reject any answer that mentions a skill not in your verified profile |
| **Generate by selection** | Pick from approved items instead of writing new text (tailored resume = choose verified bullets) |

ARGUS leans on the strongest two: **verification** and **selection**.

---

## RAG — Retrieval-Augmented Generation

**RAG** combines search with generation:

```
question ──► 1. RETRIEVE relevant documents (often via embeddings)
                       │
                       ▼
             2. AUGMENT the prompt with them ("Use ONLY these facts: …")
                       │
                       ▼
             3. GENERATE an answer grounded in the retrieved text
```

Why it's popular:
- The model can use **current** and **private** data it was never trained on.
- No retraining needed: update the documents and the answers update.
- Answers can cite their sources.

Key design choices:
- **Chunking**: split long documents into pieces (by section, ~200–800 tokens).
- **Retrieval**: vector search, keyword search (BM25 / PostgreSQL full-text), or both
  ("hybrid").
- **Top-k**: how many chunks to include (too few = missing facts, too many = noise and cost).
- **Re-ranking**: optionally re-order candidates with a stronger model.

---

## How ARGUS will use RAG (milestone M5)

Application forms ask questions such as *"Are you authorized to work in India?"* or *"Describe
a project where you used SQL."* The plan:

```
form question
   │  embed + nearest neighbours (pgvector HNSW on answer_library.embedding)
   ▼
top approved answers + relevant verified profile facts
   │  prompt: "Choose the best answer id from this list, or say NONE."
   ▼
LLM picks an id (constrained to the list)  ──► code fills the field with that approved text
   │
   └─ NONE ──► question goes to the "Needs answer" queue → you answer once → saved for reuse
```

Note the design: the LLM **chooses from a list of ids** instead of writing free text. A
constrained choice can't invent a qualification.

For free-text questions ("Why do you want to join?"), the model drafts from verified facts only,
and a second check rejects any claim not backed by a fact.

---

## Key takeaways

1. Hallucination is a property of LLMs; design the system to contain it.
2. Ground answers in provided evidence, allow "unknown", and verify in code.
3. RAG = retrieve relevant facts → put them in the prompt → generate from them.
4. When correctness matters, prefer **selection** over **generation**.

## In ARGUS

- Evidence fenced in prompts: `app/modules/llm/prompts.py`
- Answer library with an HNSW vector index (ready for RAG): `answer_library` in
  `app/db/migrations/0001_initial_schema.sql`
- Review-before-save for resume facts: `app/modules/resume/service.py` (parse vs import)
