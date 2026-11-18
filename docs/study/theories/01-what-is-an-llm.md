# 01 — What is an LLM?

## The one-sentence answer

A **Large Language Model (LLM)** is a program that, given some text, predicts **which piece of
text is most likely to come next**. It then repeats that prediction over and over to produce
sentences, answers, code or JSON.

Everything else — chatting, summarizing, extracting facts from a resume — is built on top of
that single ability: *next-token prediction*.

---

## Unpacking the three words

| Word | Meaning |
|---|---|
| **Large** | Billions of adjustable numbers (*parameters* or *weights*). Your Gemma 4 has ~25 billion. More parameters can store more patterns from the training data. |
| **Language** | It was trained on enormous amounts of text (web pages, books, code, documentation), so it learned grammar, facts, styles and reasoning patterns that appear in text. |
| **Model** | It is a mathematical function: numbers in → numbers out. There is no database of sentences inside it, only the learned weights. |

---

## A tiny thought experiment

Complete this sentence:

> "The capital of France is ___"

You answered "Paris" because you've seen that pattern many times. An LLM does the same thing
statistically. For the next position it computes a probability for **every** token it knows:

```
"Paris"   0.92
"the"     0.03
"located" 0.01
"Lyon"    0.004
...        (≈ 250,000 other tokens with tiny probabilities)
```

It then **picks** one (usually a high-probability one), appends it, and predicts again:

```
"The capital of France is"           → "Paris"
"The capital of France is Paris"     → "."
"The capital of France is Paris."    → <end of answer>
```

This loop is called **autoregressive generation**: each new token depends on all previous
tokens, including the ones the model just wrote itself.

---

## What a "token" is

Models don't read characters or whole words; they read **tokens**, chunks of text from a fixed
vocabulary (often 32k–260k entries):

```
"Unbelievably fast FastAPI"  →  ["Un", "believ", "ably", " fast", " Fast", "API"]
```

- Common words are usually one token, rare words get split up.
- Roughly **1 token ≈ 4 characters of English** (≈ 0.75 words).
- Everything is measured in tokens: context size, speed (tokens/second), cost and limits.

More in [02 — How LLMs work](02-how-llms-work.md).

---

## Why LLMs feel intelligent (and where they are not)

LLMs generalize surprisingly well. They can follow instructions they've never seen, translate,
summarize, write code and extract structured data. That's because predicting text *well*
requires internally modelling a lot about the world and about language.

But remember what they **are**:

| They are good at | They are bad at |
|---|---|
| Understanding messy human text | Exact arithmetic and counting |
| Reformatting / extracting / classifying text | Knowing facts after their training cut-off |
| Following instructions and formats | Saying "I don't know" without being told how |
| Fuzzy matching of meaning | Guaranteeing truth — they produce *plausible* text |

That last point is the most important: **an LLM produces text that *sounds* right. It has no
built-in notion of "true".** When it confidently produces something false, that is called a
**hallucination** ([08 — RAG & grounding](08-rag-grounding-hallucination.md)).

---

## Types of models you'll meet

| Type | What it does | Example |
|---|---|---|
| **Base model** | Raw next-token predictor trained on internet text. Continues text; doesn't follow instructions well. | `gemma-4-26b` (base) |
| **Instruction-tuned / chat model** | Base model further trained to follow instructions and chat. The `-it` in your model name. | `gemma4:26b-a4b-it-qat` |
| **Reasoning ("thinking") model** | Trained to write out intermediate reasoning before the answer | Gemma 4 with `think: true` |
| **Embedding model** | Not a text generator. It turns text into a vector of numbers that captures meaning. | `nomic-embed-text` (768 numbers per text) |
| **Multimodal model** | Also accepts images (or audio) | Gemma 4 lists `vision` as a capability |

ARGUS uses **two** models: a chat model (Gemma 4 26B) to read and write text, and an embedding
model (nomic-embed-text) to compare meanings.

---

## Local vs cloud LLMs

| | Local (what ARGUS uses) | Cloud API (OpenAI, Anthropic, Google…) |
|---|---|---|
| Where it runs | Your GPU (RTX 4080) via Ollama | Provider's data centre |
| Cost | Free after download (electricity) | Per token |
| Privacy | Your resume never leaves the machine | Data is sent to a third party |
| Quality | Good open models (26B) | Usually the strongest models |
| Speed | ~60 tokens/s on your GPU | Often faster |
| Control | Full: tune, inspect, modify, fine-tune | Limited to what the API exposes |

ARGUS chose local because of the project's rules: **free** and **private by default**.

---

## Key takeaways

1. An LLM is a next-token predictor; generation is that prediction run in a loop.
2. It works on **tokens**, not words or characters.
3. It is fluent, not truthful — systems around it must check its output.
4. Use the right model type for the job: chat models generate, embedding models compare.

## In ARGUS

- Chat model calls: `argus/backend/app/modules/llm/client.py`
- Which models are configured: `argus/.env` (`ARGUS_LLM_CHAT_MODEL`, `ARGUS_LLM_EMBED_MODEL`)
- Try it: UI → **LLM Lab**, or [projects/07 — Hands-on labs](../projects/07-hands-on-labs.md)
