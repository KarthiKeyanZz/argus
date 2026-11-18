# 04 — The inference stack on your machine

## Hardware

| Part | Spec | Why it matters |
|---|---|---|
| GPU | NVIDIA RTX 4080 Laptop, **12 GB VRAM**, CUDA (driver 580) | Holds model layers + KV cache; decode speed |
| CPU | Intel i9-14900HX (32 threads) | Runs any layers that don't fit on the GPU |
| RAM | 31 GB | Room for offloaded layers, Postgres, browser |
| Disk | NVMe SSD | Model load time (~15 GB read) |

## Software

```
Ollama 0.40.16   ~/.local/opt/ollama   (user install, no sudo)
  └─ systemd user unit: ~/.config/systemd/user/ollama.service
       OLLAMA_HOST=127.0.0.1:11434      # never exposed to the network
       OLLAMA_FLASH_ATTENTION=1         # memory-efficient attention
       OLLAMA_KV_CACHE_TYPE=q8_0        # 8-bit KV cache → ~half the cache memory
       OLLAMA_MAX_LOADED_MODELS=2       # chat + embedding models together
       OLLAMA_NUM_PARALLEL=1            # single user, least memory
       OLLAMA_KEEP_ALIVE=15m            # unload after 15 idle minutes
Models (~/.ollama/models):
  gemma4:26b-a4b-it-qat   15 GB on disk   25.2B params, Q4_0, MoE ~4B active, 262k max ctx
  nomic-embed-text        274 MB          137M params, 768-dim embeddings
  argus-extractor         (Modelfile variant of gemma4 — same weights, no extra space)
```

Commands:

```bash
systemctl --user start|stop|status ollama
systemctl --user disable ollama        # don't auto-start at login
make llm-status                        # installed + loaded models + GPU memory
ollama ps                              # what's loaded, CPU/GPU split, context size
ollama show gemma4:26b-a4b-it-qat      # model card
make llm-gpu                           # live GPU memory while experimenting
```

---

## Measured performance (2026-11-13)

| Test | Result |
|---|---|
| GPU placement (`ollama ps`, num_ctx 8192) | 97% GPU / 3% CPU |
| VRAM reported in the LLM Lab while loaded | gemma ≈ 8.5 GB, nomic ≈ 0.1 GB |
| Cold start (first call after boot) | load ≈ 24 s; first answer ≈ 57 s incl. one-time GPU warm-up |
| Warm generation, 200-token answer | **~60 tokens/s** decode, ~170 tokens/s prefill, 3.5 s total |
| Job extraction, `think: false` | **4–9 s**, ~44–56 tokens/s |
| Same extraction, thinking on (default) | ~23 s, same facts |
| Resume parse (727 output tokens) | ~12.5 s at ~60 tokens/s |
| Puzzle, `think: false` / `true` | 0.4 s / 5.6 s (335 reasoning tokens) |
| LLM Lab playground short answer | 1.3 s at 63.5 tokens/s |
| Embeddings (4 texts) | well under a second |

> Open question worth investigating as an exercise: the model file is ~15 GB, yet the resident
> size reported was lower (8.5–9.4 GB). Possible reasons include parts that aren't loaded for
> text-only use (Gemma 4 also has vision capability) and how Ollama reports memory. Use
> `ollama ps`, `nvidia-smi` and the server logs (`journalctl --user -u ollama`) to find out.

---

## Why this model is fast on this GPU

1. **MoE**: ~4B active parameters per token → little data to stream per token
   ([theories/04](../theories/04-inference.md)).
2. **4-bit QAT** weights: small, with most quality kept.
3. **Almost fully on the GPU** (97%): CPU offload would dominate the time otherwise.
4. **Small context (8k) + 8-bit KV cache + FlashAttention**: less memory → more layers on the GPU.
5. **`think: false`** for extraction: no hidden reasoning tokens.

## Things that make it slow (try them in the LLM Lab)

| Change | Expected effect |
|---|---|
| `num_gpu: 0` | Everything on CPU → tokens/s collapses |
| `num_ctx: 32768` | Bigger KV cache → less GPU room → slower, more VRAM |
| `think: on` | Many more output tokens → seconds become tens of seconds |
| First call after 15 idle minutes | Model reload (~24 s) |
| Long outputs | Decode time grows linearly with tokens |

## Fallbacks if you ever need more speed

| Option | Trade-off |
|---|---|
| `gemma4:12b` (~7.5 GB) | Fits fully in VRAM with more context room; somewhat lower quality |
| Smaller `num_ctx` (4096) for short inputs | Can't handle long postings |
| Distilled small extractor (planned) | Needs a fine-tuning project ([08](08-future-llm-work.md)) |

Switching models is one setting: `ARGUS_LLM_CHAT_MODEL` in `argus/.env`.
