# 04 — Inference: running a trained model

**Inference** = using a trained model to produce outputs. Training happens once (by Google, for
Gemma); inference happens every time ARGUS reads a resume or a job posting. Inference
performance decides whether a feature feels instant or unusable.

---

## The two phases of every request

```
                 ┌──────────── PREFILL ────────────┐ ┌──────── DECODE ────────┐
 prompt tokens:  [t1 t2 t3 ... t900] processed together   → token → token → token ...
                 compute-bound, parallel, fast            memory-bound, one at a time
 measured as:    prompt_tokens_per_s  (~170+ on your GPU)  output_tokens_per_s (~60)
```

| | Prefill | Decode |
|---|---|---|
| What happens | Reads the whole prompt in one big parallel pass and builds the KV cache | Generates one token per step; each step reruns the network for 1 new token |
| Limited by | GPU compute (FLOPs) | **Memory bandwidth**: every step must read all *active* weights from VRAM |
| Implication | Long prompts are relatively cheap | Long answers are expensive → keep outputs short |

**Time to first token (TTFT)** ≈ load time + prefill time. **Throughput** ≈ decode tokens/second.

---

## Why decode is memory-bound, and why MoE helps

To produce one token, the GPU must stream the active weights through its compute units.
Roughly:

```
max decode speed ≈ memory bandwidth / bytes of active weights per token
```

- A dense 26B model at 4-bit ≈ 13 GB of weights to read **per token**.
- Your MoE model only activates ~4B parameters per token ≈ 2 GB per token.

That's why a "26B" model reaches **~60 tokens/s** on a laptop GPU. (The formula is a rough
upper bound; real engines have overheads.)

---

## The KV cache

During attention, every token produces **key** and **value** vectors. Without caching, each
decode step would recompute them for the whole sequence: O(n²) work overall. The **KV cache**
stores them so each new token computes only its own K and V.

Cost: memory that grows linearly with context length.

```
KV cache bytes ≈ 2 (K and V) × layers × kv_heads × head_dim × bytes_per_value × tokens
```

That is why:
- `num_ctx: 32768` uses far more VRAM than `num_ctx: 8192`, even for a short prompt (the
  engine reserves space for the whole window).
- Your Ollama service sets `OLLAMA_KV_CACHE_TYPE=q8_0`: the cache is stored in 8-bit instead of
  16-bit, roughly halving its size.
- `OLLAMA_FLASH_ATTENTION=1` enables **FlashAttention**, an attention algorithm that avoids
  building the full n×n score matrix in memory.

---

## Model memory: weights + cache + overhead

```
VRAM needed ≈ weights (quantized) + KV cache (num_ctx) + activations/overhead
```

If it doesn't fit, Ollama/llama.cpp **offloads** some layers to system RAM and runs them on the
CPU, which is much slower. `ollama ps` shows the split (e.g. `3%/97% CPU/GPU`). The `num_gpu`
option can force fewer layers onto the GPU — try `num_gpu: 0` in the LLM Lab to feel the
difference.

---

## Quantization — making weights smaller

Weights are trained as 16-bit floats. **Quantization** stores them with fewer bits:

| Format | Bits / weight | 26B model size | Quality |
|---|---|---|---|
| BF16 / FP16 | 16 | ~52 GB | reference |
| Q8_0 | ~8.5 | ~28 GB | nearly identical |
| Q4_K_M / Q4_0 | ~4.5 | ~15–16 GB | small loss |
| Q4 + **QAT** | ~4.5 | ~15 GB | loss mostly recovered (trained for it) |
| Q2 / Q3 | 2–3 | smaller | noticeable degradation |

How it works (simplified): weights are split into small blocks (e.g. 32 values). Each block
stores one scale factor plus small integers:

```
original:   [0.12, -0.53, 0.31, ...]       (16-bit each)
quantized:  scale = 0.0353, ints = [3, -15, 9, ...]   (4-bit each)
restored:   int × scale ≈ original
```

**GGUF** is the file format llama.cpp/Ollama use for quantized models. The names
(`Q4_0`, `Q4_K_M`, `Q8_0`) describe the scheme.

---

## Batching and parallel requests

Servers improve throughput by processing several requests at once (**batching**). Your Ollama
is set to `OLLAMA_NUM_PARALLEL=1`, which is simplest and uses the least memory, because ARGUS is a
single user. The ARGUS worker therefore processes LLM tasks one at a time.

---

## Model loading and keep-alive

Loading ~15 GB from disk into VRAM takes time (measured: **~24 s** cold, plus GPU warm-up on the
very first request). Ollama keeps the model loaded for `keep_alive` (ARGUS uses 15 minutes)
after the last request, then unloads it to free the GPU.

- `llm.warmup` task (Dashboard → "Warm up LLM") loads it in advance.
- `OLLAMA_MAX_LOADED_MODELS=2` lets the chat model and the embedding model stay loaded together.

---

## Inference engines

| Engine | Notes |
|---|---|
| **llama.cpp** | C/C++ engine for GGUF models; runs on CPU, CUDA, Metal, Vulkan. Ollama uses it (your `ollama ps` showed `llamacpp` as the runner). |
| **Ollama** | User-friendly server around llama.cpp (plus its own engine for some models): model registry, REST API, Modelfiles. **What ARGUS uses.** |
| vLLM, SGLang | High-throughput servers for many concurrent users (paged attention, continuous batching) |
| HF `transformers` | Python library; flexible, used for research and fine-tuning; slower for serving |

---

## Measuring inference — the metrics ARGUS returns

Every `/api/v1/llm/*` response includes:

| Field | Meaning |
|---|---|
| `load_ms` | Time to load the model (≈0 when warm) |
| `prompt_tokens`, `prompt_ms`, `prompt_tokens_per_s` | Prefill |
| `output_tokens`, `output_ms`, `output_tokens_per_s` | Decode |
| `total_ms` | Everything |
| `done_reason` | `stop` (finished) or `length` (hit `num_predict` → answer was cut off) |

Benchmarks on your machine are in
[projects/04 — Inference stack](../projects/04-inference-stack-on-your-machine.md).

---

## Key takeaways

1. Prefill (reading) is parallel and fast; decode (writing) is sequential and slow.
2. Decode speed is bounded by memory bandwidth ÷ active weight size → MoE and quantization help.
3. The KV cache trades memory for speed; `num_ctx` controls its size.
4. If weights + cache don't fit in VRAM, layers move to the CPU and speed drops sharply.

## In ARGUS

- Metrics conversion: `metrics_from()` in `app/modules/llm/service.py`
- Ollama service settings: `~/.config/systemd/user/ollama.service`
- Warm-up task: `llm_warmup` in `app/worker/handlers.py`
