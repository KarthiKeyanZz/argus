# 09 — Tuning & modifying models

"Tuning" means very different things depending on *what* you change. Here's the full ladder,
from free and instant to expensive and permanent.

```
cheap, reversible ───────────────────────────────────────────────► expensive, permanent
 1. inference      2. prompt &        3. Modelfile      4. fine-tuning      5. merging /
    parameters        schema             (baked            (LoRA / QLoRA /     distillation /
    (temperature…)    engineering        defaults)         full)               pretraining
```

**Rule:** exhaust levels 1–3 before reaching for 4. Most "the model is bad at X" problems are
prompt, schema or parameter problems. All six ARGUS bugs so far were fixed at levels 1–3.

---

## Level 1 — Inference parameters

Change *how* tokens are chosen, per request, with no change to the model.

| Knob | Typical effect |
|---|---|
| `temperature`, `top_k`, `top_p`, `min_p` | determinism ↔ creativity |
| `repeat_penalty` | fewer loops (careful with JSON) |
| `num_ctx` | context size ↔ memory ↔ speed |
| `num_predict` | maximum output length (also a safety cap) |
| `num_gpu` | layers on GPU vs CPU |
| `think` | reasoning on/off (quality vs time) |
| `seed` | reproducibility |

Details: [05 — Sampling](05-sampling-and-decoding.md), [04 — Inference](04-inference.md).

---

## Level 2 — Prompt & schema engineering

Change *what you ask* and *what shape the answer can take*:
system prompt rules, few-shot examples, delimiters, field order, `enum`, `pattern`,
`maxItems`, all-keys-required. Details:
[06 — Prompting & structured output](06-prompting-and-structured-output.md).

---

## Level 3 — Modelfile: a "tuned" model name without training

An Ollama **Modelfile** bakes defaults into a new model name. It reuses the same weights, so it
takes no extra disk space:

```dockerfile
FROM gemma4:26b-a4b-it-qat
PARAMETER temperature 0
PARAMETER num_ctx 8192
PARAMETER num_predict 1024
SYSTEM """You are a precise information-extraction engine..."""
```

```bash
ollama create argus-extractor -f llm/Modelfile.extractor
```

Other Modelfile instructions: `TEMPLATE` (override the chat template), `ADAPTER` (attach a LoRA
adapter — see level 4), `MESSAGE` (bake in example conversations), `LICENSE`.

This is configuration, not learning: the model's knowledge and abilities are unchanged.

---

## Level 4 — Fine-tuning: actually changing weights

Fine-tuning continues training on **your** examples so the model gets better at **your** task.

### When it's worth it

| Good reasons | Bad reasons |
|---|---|
| A narrow, repetitive task (e.g. job extraction) where a **small** model could match a big one → 5–10× faster | "Teach it facts about me" (use RAG / the prompt instead) |
| Consistent style or format that prompting can't reach | You haven't tried better prompts yet |
| Hundreds to thousands of high-quality examples available | You have 20 examples |
| Need to run on smaller hardware | One-off tasks |

### Full fine-tuning vs parameter-efficient fine-tuning (PEFT)

**Full fine-tuning** updates every weight. It needs memory for weights + gradients + optimizer
state (often 3–4× the model size in 16-bit), which rules out a 12 GB GPU for anything but tiny
models.

**LoRA (Low-Rank Adaptation)** freezes the original weights and trains small add-on matrices:

```
original layer:   y = W·x                      W: 4096 × 4096  (16.7M numbers, frozen)
with LoRA:        y = W·x + (B·A)·x            A: r × 4096, B: 4096 × r   (r = 16 → 131k numbers, trained)
```

- Trains ~0.1–1% of the parameters → far less memory, fast.
- Produces an **adapter** file (tens of MB) that is loaded on top of the base model.
- Rank `r` controls capacity (8–64 typical); `alpha` scales the update.

**QLoRA** loads the frozen base model in **4-bit** and trains LoRA adapters in higher precision.
That's what makes fine-tuning ~7–8B models feasible on a single consumer GPU like your 12 GB
RTX 4080.

### The fine-tuning workflow

```
1. DATA        2,000+ examples:  {input: posting text, output: correct JobFacts JSON}
               (bootstrap: let Gemma 26B label postings, then review/correct a subset)
2. SPLIT       train 80% / validation 10% / test 10%  (test set NEVER used for training)
3. TRAIN       QLoRA on a small base (e.g. 1–4B instruct model), a few epochs
               tools: Hugging Face transformers + PEFT + TRL, or Unsloth (free, memory-efficient)
4. EVALUATE    same test set for the small model and for Gemma 26B → compare accuracy & speed
5. EXPORT      merge adapter or keep it separate → convert to GGUF (llama.cpp tools) → quantize
6. SERVE       Modelfile:  FROM <base gguf>   ADAPTER <adapter>   → ollama create
7. MONITOR     keep measuring on new data; retrain when accuracy drifts
```

Watch out for:
- **Overfitting**: great on training data, worse on new data → watch validation loss.
- **Catastrophic forgetting**: narrow training can degrade general ability (fine for a
  single-purpose extractor).
- **Data leakage**: test examples in training → fake great results.
- **Licences**: check the base model's licence for fine-tuning and distribution (Gemma 4 is
  listed as Apache 2.0 in Ollama's library).

### Instruction tuning vs preference tuning (for your own models)

- **SFT** (supervised fine-tuning): input → ideal output pairs. What you'd do for extraction.
- **DPO**: (prompt, better answer, worse answer) triples. Useful for style or quality preferences.

---

## Level 5 — Bigger modifications

| Technique | What it is |
|---|---|
| **Distillation** | Train a small student to imitate a big teacher's outputs (the plan above is distillation via SFT). |
| **Model merging** | Combine weights of several fine-tunes (e.g. averaging, SLERP, TIES) to blend skills without training. |
| **Continued pretraining** | More next-token training on a domain corpus (e.g. millions of job postings) before SFT. Expensive. |
| **Quantization** | Not training but a modification: smaller weights for faster inference ([04](04-inference.md)). |
| **Pruning** | Remove weights or whole layers/experts that contribute little; usually followed by healing fine-tunes. |

---

## Decision guide

```
Is the output format wrong?            → schema / constrained decoding (level 2)
Is it inventing facts?                 → grounding + "null allowed" + verification (level 2 + code)
Is it too random / too repetitive?     → sampling params (level 1)
Is it too slow?                        → think off, smaller num_ctx, warm model (level 1)
                                         → still too slow at scale? distil into a small model (level 4)
Is it consistently wrong on a narrow task despite good prompts and examples?
                                       → collect data, measure, then fine-tune (level 4)
```

## In ARGUS

- Level 1: `LLMOptions` — every knob, documented in Swagger and the LLM Lab
- Level 2: `app/modules/llm/prompts.py`, `schemas.py`, `structured.py`
- Level 3: `argus/llm/Modelfile.extractor` (`make llm-create`)
- Level 4: planned — see [projects/08 — Future LLM work](../projects/08-future-llm-work.md)
