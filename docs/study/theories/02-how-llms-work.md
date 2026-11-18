# 02 — How an LLM works inside

This chapter opens the box. You don't need the maths to *use* an LLM, but knowing the moving
parts explains almost every behaviour you'll see: speed, memory use, context limits, why
`temperature` exists, and why long prompts are cheaper than long answers.

---

## The full pipeline

```
 "Junior Python developer"
          │
   1. TOKENIZER ─────────────► [ 41323, 13325, 16353 ]          (integers)
          │
   2. EMBEDDING LOOKUP ──────► one vector per token, e.g. 2,816 numbers each
          │
   3. TRANSFORMER LAYERS ────► N repeated blocks, each:
          │                      ├─ self-attention   (tokens look at earlier tokens)
          │                      └─ feed-forward MLP (per-token "thinking"/memory)
          │
   4. OUTPUT HEAD ───────────► a score ("logit") for EVERY token in the vocabulary
          │
   5. SOFTMAX ───────────────► probabilities that sum to 1
          │
   6. SAMPLING ──────────────► choose one token → append → repeat from step 3
```

(The vector size and token ids above are illustrative; every model has its own.)

---

## Step 1 — Tokenization

A **tokenizer** splits text into tokens using a fixed vocabulary learned before training
(commonly with algorithms such as *Byte-Pair Encoding*, BPE, or *SentencePiece*).

- Frequent strings ("the", " Python") become single tokens.
- Rare strings get split into smaller pieces, down to bytes if needed, so **any** text can be
  encoded.
- The tokenizer is part of the model: you can't swap it independently.

Practical consequences:
- Counting characters inside a word is hard for an LLM, because it never sees individual letters.
- Numbers are often split oddly (`"12345"` → `"123"`, `"45"`), one reason arithmetic is weak.
- Prices and limits are measured in tokens.

---

## Step 2 — Embeddings (inside the model)

Each token id is mapped to a learned vector of floating-point numbers (its **embedding**).
Tokens with related meanings end up with vectors pointing in similar directions.

The model also needs **position information**: "dog bites man" ≠ "man bites dog". Modern models
typically use **RoPE** (rotary position embeddings), which rotates vectors by an amount that
depends on position. This is also what makes very long context windows possible.

> Don't confuse these internal embeddings with an **embedding model**
> ([07](07-embeddings-and-vector-search.md)), which outputs one vector for a whole text.

---

## Step 3 — The transformer layers

The core architecture is the **transformer** (Vaswani et al., 2017, *"Attention Is All You
Need"*). A model stacks dozens of identical **blocks**. Each block has two sub-layers.

### 3a. Self-attention — "which earlier tokens matter for this one?"

For every token, the layer computes three vectors:

| Vector | Intuition |
|---|---|
| **Query (Q)** | "What am I looking for?" |
| **Key (K)** | "What do I contain?" |
| **Value (V)** | "What information do I pass on if chosen?" |

Each token compares its **query** with the **keys** of all earlier tokens (a dot product).
Higher scores mean more relevant. The scores become weights (softmax), and the token gathers a
weighted mix of their **values**:

```
attention(Q, K, V) = softmax( Q·Kᵀ / √d ) · V
```

Example. In *"Python developer with 2 years of experience in it"*, when processing `it` the
attention weights might focus on `Python` — that's how the model resolves what "it" refers to.

- **Multi-head attention** runs several attention "heads" in parallel; each can specialize
  (syntax, coreference, long-range facts…).
- **Causal mask**: a token may only look at tokens *before* it, never after. That is what makes
  the model a left-to-right generator.

> **Complexity note.** Every token attends to every earlier token, so attention costs grow
> with the **square** of sequence length — O(n²). (Yes, the thing we ban in ARGUS code is at
> the heart of every LLM.) Engines fight this with the **KV cache**, **FlashAttention**, and
> **sliding-window attention** (each token only looks at a fixed recent window in some
> layers; earlier Gemma generations mixed local-window and global layers).
> See [04 — Inference](04-inference.md).

### 3b. Feed-forward network (MLP) — "think about it"

After attention mixes information *between* tokens, a feed-forward network transforms each
token's vector *individually*. Much of a model's factual "knowledge" is thought to be stored in
these layers. They hold most of the parameters.

### 3c. Residuals and normalization

Each sub-layer **adds** its output to its input (a *residual connection*) and normalizes the
values. That's what lets a model be 40+ layers deep and still train stably.

### Mixture-of-Experts (MoE) — your model's special trick

In an MoE model the feed-forward part is replaced by **many smaller expert networks** plus a
tiny **router**. For each token the router picks a few experts, and only those run:

```
token ──► router ──► expert 3 ─┐
                └──► expert 17 ─┴─► combined output        (the other experts are skipped)
```

Your model `gemma4:26b-a4b` has ~26B parameters in total but only **~4B active per token**
(`a4b`). Result: the knowledge capacity of a big model at the per-token compute cost of a small
one. Catch: **all** experts must be loaded in memory, because any token may need any expert.

---

## Step 4–5 — Logits and softmax

The final layer outputs one raw score (**logit**) per vocabulary entry. **Softmax** turns them
into probabilities:

```
p(token_i) = e^(logit_i) / Σ_j e^(logit_j)
```

Big logit gaps → one token dominates. Small gaps → many plausible options.

---

## Step 6 — Sampling

The program running the model (not the model itself) chooses the next token from those
probabilities. *Temperature*, *top-k*, *top-p* and similar settings control that choice. That's
the most important tuning lever you have at inference time — covered in
[05 — Sampling & decoding](05-sampling-and-decoding.md).

---

## The context window

The **context window** is the maximum number of tokens the model can attend to at once
(prompt + everything generated so far).

- Gemma 4 supports up to **262,144 tokens** (reported by `GET /api/v1/llm/models/{name}`).
- ARGUS deliberately uses **8,192** (`num_ctx`), because larger windows need more memory (the
  KV cache), which would push model layers off your 12 GB GPU.
- If input exceeds the window, it must be truncated or summarized. ARGUS truncates long
  postings to `llm_max_input_chars` (24,000 characters ≈ 6,000 tokens).

---

## The chat template

Chat models are trained with special tokens marking who is speaking. When you send:

```json
[{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]
```

the engine renders it through the model's **chat template** into one long token sequence,
roughly:

```
<start_of_turn>system\nBe brief.<end_of_turn>\n<start_of_turn>user\nHi<end_of_turn>\n<start_of_turn>model\n
```

and the model continues from there. (Exact markers differ per model family.) You can see your
model's real template in the LLM Lab or via `GET /api/v1/llm/models/{name}` → `template`.

---

## Key takeaways

1. Text → tokens → vectors → transformer layers → logits → probabilities → one sampled token.
2. **Attention** lets tokens use earlier context; it's quadratic in length, which is why
   context size costs memory and time.
3. **MoE** = big knowledge, small per-token compute, but full memory footprint.
4. Sampling happens *outside* the network and is fully under your control.

## In ARGUS

- Context size setting: `ARGUS_LLM_DEFAULT_NUM_CTX` → `app/core/config.py`
- Model card (context length, template, capabilities): `GET /api/v1/llm/models/{name}`
- Truncation of long inputs: `LLMService.extract_job` in `app/modules/llm/service.py`
