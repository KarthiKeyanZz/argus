# 05 — Sampling & decoding: how the next token is chosen

After the model outputs probabilities for every token in its vocabulary, *something* must pick
one. That "something" is the **sampler**, and its settings are the main inference-time tuning
knobs. They don't change the model at all — only how its output is used.

---

## Greedy decoding

Always take the most probable token.

```
probabilities: "Paris" 0.92 · "the" 0.03 · "Lyon" 0.004 ...
greedy pick:   "Paris"
```

- ✅ Deterministic: same input → same output.
- ✅ Best for **extraction** and classification, where there is one right answer.
- ❌ Can get stuck in **repetition loops**: once a pattern starts, repeating it is often the
  most probable continuation. (This happened in ARGUS — see
  [projects/06](../projects/06-tuning-case-study.md), bug 1.)
- ❌ Bland for creative writing.

`temperature: 0` in Ollama means greedy.

---

## Temperature — sharpen or flatten

Temperature divides the logits before softmax:

```
p_i = softmax(logit_i / T)
```

| T | Effect | Example distribution for "Paris / the / Lyon" |
|---|---|---|
| 0 | Greedy: only the top token | 1.00 / 0 / 0 |
| 0.3 | Sharper, rarely surprising | 0.99 / 0.01 / ~0 |
| 1.0 | The model's raw distribution | 0.92 / 0.03 / 0.004 |
| 1.5+ | Flatter: rare tokens get real chances, coherence drops | 0.70 / 0.10 / 0.04 |

(Numbers illustrative.) Rule of thumb: **0 for facts, 0.6–0.9 for natural writing, >1.2 for
brainstorming** (and expect nonsense).

---

## Truncation samplers — cut off the long tail

Even at T=1, there are ~250k tokens with tiny probabilities. Sampling one of them occasionally
derails the output. Truncation keeps only plausible candidates:

| Sampler | Keeps | Typical value |
|---|---|---|
| **top_k** | The k most likely tokens | 40–64 |
| **top_p** (nucleus) | The smallest set whose probabilities sum to ≥ p | 0.9–0.95 |
| **min_p** | Tokens with probability ≥ min_p × (top token's probability) | 0.05–0.1 |

`min_p` adapts to confidence. When the model is sure (top = 0.9), it keeps very few tokens;
when it's unsure (top = 0.2), it keeps many. Many people now prefer it to top_p.

Gemma's defaults (from its model card in Ollama): `temperature 1, top_k 64, top_p 0.95`.

---

## Penalties — discourage repetition

| Option | Effect |
|---|---|
| `repeat_penalty` | Lowers the logits of tokens that appeared recently (>1 = penalize). |
| `repeat_last_n` | How many recent tokens the penalty looks at. |
| presence/frequency penalties (other APIs) | Penalize any reuse / penalize in proportion to count. |

⚠ Penalties can **break structured output**: JSON needs repeated `"`, `:` and `,`. ARGUS uses
`repeat_penalty 1.0` (off) for extraction and relies on schema limits (`maxItems`) to stop
loops instead.

---

## Order of operations

Every engine runs **penalties → filters (top_k / top_p / min_p) + temperature → random draw**,
but the exact order differs:

- Hugging Face `transformers`: temperature, then top-k / top-p.
- llama.cpp (used by Ollama for your model): penalties, then the truncation filters, with
  temperature applied near the end of the chain.

Practical consequence: the same numbers can behave slightly differently across engines. What
never changes: **at temperature 0 decoding is greedy**, so the other samplers stop mattering.

---

## Seed — reproducible randomness

Sampling uses a pseudo-random generator. A fixed **seed** makes the "random" choices repeatable:
same prompt + same options + same seed + same model + same engine = same output. ARGUS sets
`seed: 7` for extraction, and a live test checks reproducibility
(`tests/llm/test_live_model.py`).

(Tiny numerical differences on different hardware or engine versions can still change outputs.
Determinism is "practically repeatable", not a mathematical guarantee.)

---

## Stopping

Generation ends when:
1. the model emits its **end-of-turn token** → `done_reason: "stop"`
2. a `stop` string you supplied appears
3. `num_predict` tokens were generated → `done_reason: "length"` (output is **truncated**)

ARGUS treats `length` on extraction as a **failure** and discards the result: truncated JSON is
invalid, and hitting the cap usually means the model was looping.

---

## Other decoding strategies (good to know)

| Strategy | Idea | Used for |
|---|---|---|
| Beam search | Keep the best *k* partial sequences, return the best full one | Translation, older systems; rarely for chat |
| **Constrained decoding** | Mask tokens that would violate a grammar / JSON Schema | Guaranteed-valid JSON → [06](06-prompting-and-structured-output.md) |
| Speculative decoding | A small draft model proposes tokens, the big model verifies several at once | Speed-ups without quality loss |

---

## Choosing settings — cheat sheet

| Task | temperature | others | think |
|---|---|---|---|
| Extract facts (resume, job posting) | 0 | seed fixed, `num_predict` capped, JSON schema | off |
| Classify an email | 0 | enum schema | off |
| Draft a cover letter | 0.6–0.8 | top_p 0.9 or min_p 0.05 | optional |
| Brainstorm | 1.0–1.2 | min_p 0.05 | off |
| Tricky reasoning (ambiguous form question) | 0–0.3 | — | on |

## In ARGUS

- Options model with explanations: `LLMOptions` in `app/modules/llm/schemas.py`
- Extraction defaults (temperature 0, seed 7, `num_predict` 1536): `app/modules/llm/service.py`
- Try every knob with live speed metrics: UI → **LLM Lab**
