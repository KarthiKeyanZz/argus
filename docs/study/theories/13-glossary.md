# 13 — Glossary

| Term | Meaning | More |
|---|---|---|
| **Activation** | Intermediate values computed inside the network for a given input | 02 |
| **Adapter (LoRA)** | Small trained weight matrices loaded on top of a frozen base model | 09 |
| **Agent** | LLM in a loop that chooses actions/tools until a goal is met | 11 |
| **ANN** | Approximate nearest-neighbour search (e.g. HNSW) | 07 |
| **Attention** | Mechanism letting each token weigh earlier tokens (Q·K → weights → mix of V) | 02 |
| **Autoregressive** | Generates one token at a time, each conditioned on all previous tokens | 01 |
| **Base model** | Pretrained next-token predictor, not instruction-tuned | 03 |
| **BF16 / FP16** | 16-bit floating-point formats for weights | 04 |
| **Calibration** | Choosing thresholds from measured data | 10 |
| **Chain-of-thought** | Model writes intermediate reasoning before answering | 06 |
| **Chat template** | Special-token format that wraps system/user/assistant messages | 02 |
| **Constrained decoding** | Masking tokens so output must match a grammar / JSON Schema | 06 |
| **Context window** | Max tokens (input + output) the model can attend to | 02 |
| **Cosine similarity** | Angle-based closeness of two vectors (1 = same direction) | 07 |
| **Cross-entropy loss** | Training objective: how wrong the predicted next-token probability was | 03 |
| **Decode** | Generating output tokens one by one; memory-bandwidth-bound | 04 |
| **Distillation** | Training a small model to imitate a large one | 03, 09 |
| **DPO** | Direct Preference Optimization: tuning on preferred vs rejected answers | 03 |
| **Embedding** | Vector of numbers representing meaning (of a token, or of a whole text) | 02, 07 |
| **Embedding model** | Model that outputs one vector per text, for comparison/search | 07 |
| **Epoch** | One pass over the training data | 09 |
| **Few-shot** | Including examples in the prompt | 06 |
| **Fine-tuning** | Continuing training on task-specific data | 09 |
| **FlashAttention** | Memory-efficient attention algorithm | 04 |
| **GBNF** | llama.cpp grammar format used for constrained decoding | 06 |
| **GGUF** | File format for (quantized) models used by llama.cpp/Ollama | 04 |
| **Greedy decoding** | Always pick the most probable token (temperature 0) | 05 |
| **Grounding** | Making answers come from provided evidence, and checking it | 08 |
| **Hallucination** | Fluent but false/unsupported output | 08 |
| **HNSW** | Graph-based ANN index, ~O(log n) search | 07 |
| **Inference** | Running a trained model to get outputs | 04 |
| **Instruction tuning (SFT)** | Fine-tuning on instruction → ideal-answer pairs | 03 |
| **KV cache** | Stored keys/values of past tokens to avoid recomputation | 04 |
| **Latency / TTFT** | Time to respond / time to first token | 04 |
| **Logits** | Raw scores per vocabulary token before softmax | 02 |
| **LoRA / QLoRA** | Low-rank adapter fine-tuning / LoRA on a 4-bit base model | 09 |
| **MoE** | Mixture-of-Experts: router activates a few expert sub-networks per token | 02, 04 |
| **Modelfile** | Ollama recipe: base model + parameters + system prompt (+ adapter) | 09 |
| **min_p / top_p / top_k** | Truncation samplers that drop unlikely tokens | 05 |
| **num_ctx** | Context window size setting in Ollama | 04 |
| **num_predict** | Maximum number of output tokens | 05 |
| **Offloading** | Running some layers on the CPU when VRAM is insufficient | 04 |
| **Parameters / weights** | The learned numbers inside the model | 01 |
| **pgvector** | PostgreSQL extension for vector columns and ANN indexes | 07 |
| **Precision / recall / F1** | Correctness of positives / coverage of positives / their balance | 10 |
| **Prefill** | Processing the prompt in one parallel pass | 04 |
| **Pretraining** | Large-scale next-token training on general text | 03 |
| **Prompt injection** | Untrusted text containing instructions the model follows | 12 |
| **QAT** | Quantization-aware training: trained to tolerate low precision | 03, 04 |
| **Quantization** | Storing weights in fewer bits (e.g. 4-bit) | 04 |
| **RAG** | Retrieval-Augmented Generation: retrieve facts, put them in the prompt | 08 |
| **Reasoning / thinking model** | Trained to produce reasoning tokens before answering | 03 |
| **RLHF** | Reinforcement learning from human feedback | 03 |
| **RoPE** | Rotary position embeddings: encodes token order | 02 |
| **Sampling** | Choosing the next token from probabilities | 05 |
| **Seed** | Fixes pseudo-randomness for reproducible sampling | 05 |
| **Softmax** | Turns logits into probabilities that sum to 1 | 02 |
| **System prompt** | Standing instructions for the model | 06 |
| **Temperature** | Sharpens (<1) or flattens (>1) the probability distribution | 05 |
| **Token** | Unit of text the model reads/writes (~4 characters of English) | 01 |
| **Tokenizer** | Converts text ↔ token ids | 02 |
| **Tool calling** | Model outputs a structured request for the program to run a tool | 11 |
| **Transformer** | Architecture of stacked attention + feed-forward blocks | 02 |
| **VRAM** | GPU memory; must hold weights + KV cache for fast inference | 04 |
