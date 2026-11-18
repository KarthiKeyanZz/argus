# 03 — How LLMs are trained

Training is how the billions of weights get their values. You won't train a 26B model from
scratch (that costs millions of dollars), but knowing the stages explains what a model can and
can't do, and what *you* can change ([09 — Tuning & modifying](09-tuning-and-modifying-models.md)).

---

## The big picture

```
   random weights
        │
  ① PRETRAINING ─────────── trillions of tokens of web text, books, code
        │                    objective: predict the next token
        ▼
   BASE MODEL  (knows language + world knowledge, but just "continues text")
        │
  ② SUPERVISED FINE-TUNING (SFT / instruction tuning)
        │                    curated examples: instruction → ideal answer
        ▼
   INSTRUCT MODEL  (follows instructions, chat format)
        │
  ③ PREFERENCE TUNING (RLHF, DPO, …)
        │                    humans/AI rank answers; model learns to prefer the better ones
        ▼
   ASSISTANT MODEL  (helpful, safer, better formatted)   ← "-it" models like yours
        │
  ④ (optional) REASONING TRAINING
                             reward correct final answers on maths/code → learns to "think"
```

---

## ① Pretraining — learning language and knowledge

- **Data**: a huge, filtered mix of internet text, books, papers and code. Trillions of tokens.
- **Objective**: next-token prediction. Show the model text, hide the next token, measure how
  wrong its probability was (**cross-entropy loss**), and nudge every weight slightly to be
  less wrong (**gradient descent** via **backpropagation**).
- **Self-supervised**: the text labels itself (the "answer" is simply the next token), so no
  human labelling is needed. That is why it scales to trillions of tokens.
- **Cost**: thousands of GPUs for weeks to months.

What it produces: a **base model** that can continue any text plausibly. It has absorbed
grammar, facts, code patterns and reasoning patterns, but it doesn't *follow instructions*.
Ask it "Write a haiku about Python" and it might continue with "Write a haiku about Java"
because that looks like a list of prompts.

**Training cut-off**: the model only knows what was in its data. Anything later (new
frameworks, today's job postings) is unknown unless you put it in the prompt.

---

## ② Supervised fine-tuning (SFT) — learning to follow instructions

The base model is trained further on curated **(instruction, ideal response)** pairs:

```
User: Extract the skills from: "We need Python and SQL."
Assistant: ["python", "sql"]
```

Same next-token objective, but only on the assistant part and on a much smaller,
higher-quality dataset. This teaches the chat template, turn-taking, and following formats.

---

## ③ Preference tuning — learning what "better" means

Many answers can be "correct"; some are more helpful, honest, safe or well formatted.

| Method | How it works |
|---|---|
| **RLHF** (Reinforcement Learning from Human Feedback) | Humans rank several answers → train a **reward model** to predict those rankings → use reinforcement learning (e.g. PPO) to make the LLM produce high-reward answers |
| **DPO** (Direct Preference Optimization) | Skips the separate reward model: trains directly on (preferred, rejected) answer pairs. Simpler and popular. |
| **RLAIF / constitutional methods** | An AI model provides the preference judgements using written principles |

This stage is also where models learn to refuse harmful requests. It's why instruct models are
*eager to please*: they were rewarded for helpful-looking answers, which is one root cause of
confident hallucinations.

---

## ④ Reasoning training

"Thinking" models are additionally trained (often with reinforcement learning on problems with
checkable answers, like maths and code) to produce a chain of intermediate reasoning before the
final answer. At inference this costs extra tokens, and therefore time:

> On your machine: a puzzle took **0.4 s** with `think: false` and **5.6 s** with `think: true`,
> because 335 extra reasoning tokens were generated.

---

## Two other techniques you'll hear about

### Distillation

A large **teacher** model generates outputs (or probability distributions), and a small
**student** model is trained to imitate them. Many small models are distilled from bigger
ones. You can do a mini version yourself: have Gemma 26B label 2,000 job postings, then
fine-tune a 1–4B model on those labels ([projects/08](../projects/08-future-llm-work.md)).

### Quantization-aware training (QAT)

Normally a model is trained in 16-bit and *afterwards* compressed to 4-bit, which loses some
quality. With **QAT**, the model is trained while simulating the 4-bit rounding, so it learns
weights that survive compression. Your model's `-qat` suffix means exactly that.

---

## Why this matters to you as a builder

| Fact from training | Consequence when building |
|---|---|
| Learned from text statistics | Fluent ≠ correct → validate outputs in code |
| Training cut-off | Put current facts (the job posting, your resume) **in the prompt** |
| SFT on formats | Clear instructions + examples reliably steer the format |
| Rewarded for helpfulness | It will "fill gaps" by guessing → tell it to use `null`, and check |
| Tokens are the unit | Arithmetic and counting are weak → compute in code |

## In ARGUS

- Prompts that say "use null, never guess": `app/modules/llm/prompts.py`
- Arithmetic moved out of the model: `app/modules/resume/dates.py`
- Using the instruct (`-it`) + QAT model: `ARGUS_LLM_CHAT_MODEL` in `argus/.env`
