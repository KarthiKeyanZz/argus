"""Request/response models for the LLM endpoints.

The field descriptions double as documentation: open Swagger (/docs) and read
them next to the "Try it out" button while you experiment.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.shared.schemas import StrictModel

# ----------------------------------------------------------------------------- tuning knobs


class LLMOptions(StrictModel):
    """Sampling / runtime parameters. Omit a field to use the model's default."""

    temperature: float | None = Field(
        None,
        ge=0,
        le=2,
        description="Randomness. 0 = always pick the most likely token (deterministic, best for "
        "extraction). 0.7-1.0 = creative writing. >1.2 = increasingly incoherent.",
    )
    top_p: float | None = Field(
        None,
        gt=0,
        le=1,
        description="Nucleus sampling: sample only from the smallest set of tokens whose "
        "probabilities add up to top_p. 0.9 cuts the long tail of unlikely tokens.",
    )
    top_k: int | None = Field(
        None,
        ge=1,
        le=1000,
        description="Sample only from the k most likely tokens. Lower = safer, less varied.",
    )
    min_p: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Drop tokens whose probability is below min_p x (probability of the best "
        "token). A modern alternative to top_p; 0.05 is a common value.",
    )
    repeat_penalty: float | None = Field(
        None,
        ge=0,
        le=3,
        description="Penalize tokens that already appeared. >1 reduces loops/repetition.",
    )
    repeat_last_n: int | None = Field(
        None, ge=-1, le=4096, description="How many recent tokens the repeat penalty looks at."
    )
    seed: int | None = Field(
        None, description="Fix the random seed so the same prompt + options gives the same output."
    )
    num_ctx: int | None = Field(
        None,
        ge=512,
        le=262_144,
        description="Context window in tokens (prompt + answer). Bigger = more memory (KV cache) "
        "and slower. ~4 characters of English per token.",
    )
    num_predict: int | None = Field(
        None, ge=-1, le=32_768, description="Max tokens to generate. -1 = until the model stops."
    )
    stop: list[str] | None = Field(
        None, max_length=8, description="Stop generating when any of these strings appears."
    )
    num_gpu: int | None = Field(
        None,
        ge=0,
        le=999,
        description="How many model layers to place on the GPU (rest run on CPU). "
        "Usually leave unset; Ollama picks the max that fits in VRAM.",
    )

    def to_ollama(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class GenerationMetrics(BaseModel):
    """Timing returned by Ollama, converted from nanoseconds."""

    total_ms: float = Field(description="Wall time for the whole request.")
    load_ms: float = Field(description="Time spent loading the model into memory (0 if warm).")
    prompt_tokens: int = Field(description="Tokens in the input (after the chat template).")
    prompt_ms: float = Field(description="Time to read the prompt ('prefill').")
    prompt_tokens_per_s: float | None
    output_tokens: int = Field(description="Tokens generated.")
    output_ms: float = Field(description="Time spent generating ('decode').")
    output_tokens_per_s: float | None = Field(
        description="Generation speed. The number to watch when tuning."
    )


ThinkParam = Field(
    None,
    description="Reasoning models only: true = let the model 'think' before answering "
    "(slower, often better); false = answer directly. Unset = model default.",
)

# ----------------------------------------------------------------------------- generate / chat


class GenerateRequest(StrictModel):
    prompt: str = Field(
        min_length=1,
        max_length=100_000,
        examples=["Explain what a context window is in two sentences."],
    )
    system: str | None = Field(
        None,
        max_length=20_000,
        description="System prompt: the standing instructions / persona for the model.",
    )
    model: str | None = Field(None, description="Defaults to the configured chat model.")
    options: LLMOptions = Field(default_factory=LLMOptions)
    format: Literal["json"] | dict[str, Any] | None = Field(
        None,
        description='`"json"` forces valid JSON. A JSON Schema object forces output that '
        "matches the schema (constrained decoding).",
    )
    think: bool | None = ThinkParam


class GenerateResponse(BaseModel):
    model: str
    response: str
    thinking: str | None = Field(None, description="The model's reasoning, if think=true.")
    done_reason: str | None = Field(
        None, description="'stop' = finished; 'length' = hit num_predict."
    )
    metrics: GenerationMetrics


class ChatMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=100_000)


class ChatRequest(StrictModel):
    messages: list[ChatMessage] = Field(
        min_length=1,
        max_length=100,
        examples=[[{"role": "user", "content": "What is quantization in one paragraph?"}]],
    )
    model: str | None = None
    options: LLMOptions = Field(default_factory=LLMOptions)
    format: Literal["json"] | dict[str, Any] | None = None
    think: bool | None = ThinkParam


class ChatResponse(BaseModel):
    model: str
    message: ChatMessage
    thinking: str | None = None
    done_reason: str | None = None
    metrics: GenerationMetrics


# ----------------------------------------------------------------------------- embeddings


class EmbedRequest(StrictModel):
    inputs: list[str] = Field(
        min_length=1, max_length=256, examples=[["Python developer", "Backend engineer (Python)"]]
    )
    model: str | None = Field(None, description="Defaults to the configured embedding model.")


class EmbedResponse(BaseModel):
    model: str
    dimensions: int = Field(description="Length of each vector (768 for nomic-embed-text).")
    embeddings: list[list[float]]


class SimilarityRequest(StrictModel):
    query: str = Field(min_length=1, max_length=8_000, examples=["junior python backend developer"])
    candidates: list[str] = Field(
        min_length=1,
        max_length=256,
        examples=[
            [
                "Graduate Software Engineer - Python/Django",
                "Senior Staff Machine Learning Engineer",
                "Entry-level Backend Developer (FastAPI)",
                "Restaurant Manager",
            ]
        ],
    )
    model: str | None = None


class SimilarityHit(BaseModel):
    text: str
    score: float = Field(description="Cosine similarity: 1 = same meaning, ~0 = unrelated.")


class SimilarityResponse(BaseModel):
    model: str
    results: list[SimilarityHit] = Field(description="Sorted best match first.")


# ----------------------------------------------------------------------------- models


class ModelSummary(BaseModel):
    name: str
    size_gb: float = Field(description="Size on disk.")
    family: str | None
    parameter_size: str | None
    quantization: str | None
    loaded: bool = Field(description="Currently in memory.")
    vram_gb: float | None = Field(None, description="How much of it sits in GPU memory.")
    expires_at: str | None = Field(None, description="When it will be unloaded (keep_alive).")


class ModelList(BaseModel):
    ollama_version: str
    chat_model: str
    embed_model: str
    models: list[ModelSummary]


class ModelDetails(BaseModel):
    name: str
    family: str | None
    parameter_size: str | None
    quantization: str | None
    context_length: int | None = Field(description="Max context the model was trained for.")
    capabilities: list[str] = Field(description="e.g. completion, tools, vision, thinking.")
    default_parameters: dict[str, str] = Field(description="Defaults baked into the model.")
    template: str | None = Field(description="Chat template that wraps your messages.")
    model_info: dict[str, Any] = Field(description="Raw architecture metadata.")


# ----------------------------------------------------------------------------- job extraction

SeniorityLevel = Literal["intern", "entry", "junior", "mid", "senior", "lead", "unknown"]
EducationLevel = Literal["none", "high_school", "diploma", "bachelor", "master", "phd", "unknown"]


class JobFacts(BaseModel):
    """What the LLM must return for a job posting. Its JSON Schema is sent to Ollama
    as `format`, so the model is *forced* to produce exactly this shape.

    FIELD ORDER MATTERS: the model writes fields top to bottom and every token is
    conditioned on what it already wrote. So we ask for the summary and education
    first (degree subjects get their own slot and stop leaking into skills), then
    the years, and only then the judgement calls (seniority, entry-level).
    """

    title: str = Field(description="Job title as written in the posting.")
    summary: str = Field(description="One-sentence plain summary of the role.")
    education_level: EducationLevel
    education_fields: list[str] = Field(
        max_length=10,
        description="Degree subjects, e.g. 'computer science', 'mathematics'. NOT skills.",
    )
    min_years_experience: float | None = Field(
        description="Minimum years explicitly required, else null. Do not guess."
    )
    max_years_experience: float | None = Field(
        description="Upper bound if a range is given (e.g. 0-2 years -> 2), else null."
    )
    seniority: SeniorityLevel
    entry_level_friendly: bool = Field(
        description="True only if the posting accepts freshers / new graduates / interns "
        "/ 0-1 years."
    )
    # max_length -> "maxItems" in the JSON Schema: the grammar physically cannot emit more
    # items, which stops greedy-decoding repetition loops from running away.
    required_skills: list[str] = Field(
        max_length=30,
        description="Concrete technical skills that are required: languages, frameworks, tools, "
        "platforms, techniques. Short lowercase names.",
    )
    preferred_skills: list[str] = Field(
        max_length=30, description="Concrete technical skills that are nice-to-have / a plus."
    )
    employment_type: Literal["full_time", "part_time", "internship", "contract", "unknown"]
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"]
    location: str | None


class JobExtractionRequest(StrictModel):
    text: str = Field(
        min_length=50,
        max_length=60_000,
        description="Plain text of a job posting.",
        examples=[
            "Junior Backend Engineer (Python) - Bengaluru (Hybrid)\n"
            "We're hiring a junior engineer to build APIs with FastAPI and PostgreSQL.\n"
            "Requirements: 0-2 years of experience, Python, SQL, REST APIs, Git. "
            "Bachelor's degree in CS or related field.\nNice to have: Docker, AWS, Redis.\n"
            "Full-time. Freshers are welcome to apply."
        ],
    )
    model: str | None = None
    options: LLMOptions = Field(
        default_factory=lambda: LLMOptions(temperature=0, seed=7),
        description="Defaults to temperature 0 (deterministic).",
    )
    think: bool | None = Field(
        False,
        description="Default false: Gemma 4 thinks by default, which made extraction ~4x "
        "slower (23 s vs 5 s) with no accuracy gain on postings. Set true to compare.",
    )


class JobExtractionResponse(BaseModel):
    model: str
    prompt_version: int
    facts: JobFacts
    input_truncated: bool
    metrics: GenerationMetrics
