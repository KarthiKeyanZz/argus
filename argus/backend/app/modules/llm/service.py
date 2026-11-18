"""LLM use-cases built on the Ollama client.

The LLM is used as a *pure function*: text in -> validated data out. It has no
tools and cannot act. Anything consequential is decided by normal code.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import UpstreamError
from app.modules.llm import prompts
from app.modules.llm.client import OllamaClient
from app.modules.llm.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
    GenerationMetrics,
    JobExtractionRequest,
    JobExtractionResponse,
    JobFacts,
    LLMOptions,
    ModelDetails,
    ModelList,
    ModelSummary,
    SimilarityHit,
    SimilarityResponse,
)
from app.modules.llm.structured import llm_schema
from app.shared.text import normalize_skill, unique_preserving_order

_GB = 1024**3
EXTRACTION_MAX_TOKENS = 1536


class LLMService:
    def __init__(self, client: OllamaClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    # ------------------------------------------------------------------ helpers
    def _options(self, options: LLMOptions) -> dict[str, Any]:
        merged = {"num_ctx": self.settings.llm_default_num_ctx}
        merged.update(options.to_ollama())
        return merged

    def _base_body(
        self, model: str | None, options: LLMOptions, think: bool | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model or self.settings.llm_chat_model,
            "options": self._options(options),
            "keep_alive": self.settings.llm_keep_alive,
        }
        if think is not None:
            body["think"] = think
        return body

    # ------------------------------------------------------------------ models
    def list_models(self) -> ModelList:
        installed = self.client.list_models()
        loaded = {m["name"]: m for m in self.client.running_models()}  # O(1) lookups below
        models = []
        for m in installed:
            details = m.get("details") or {}
            running = loaded.get(m["name"])
            models.append(
                ModelSummary(
                    name=m["name"],
                    size_gb=round(m.get("size", 0) / _GB, 2),
                    family=details.get("family"),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                    loaded=running is not None,
                    vram_gb=round(running.get("size_vram", 0) / _GB, 2) if running else None,
                    expires_at=running.get("expires_at") if running else None,
                )
            )
        return ModelList(
            ollama_version=self.client.version(),
            chat_model=self.settings.llm_chat_model,
            embed_model=self.settings.llm_embed_model,
            models=models,
        )

    def model_details(self, name: str) -> ModelDetails:
        data = self.client.show(name)
        details = data.get("details") or {}
        info: dict[str, Any] = data.get("model_info") or {}
        context_length = next(
            (int(v) for k, v in info.items() if k.endswith(".context_length")), None
        )
        return ModelDetails(
            name=name,
            family=details.get("family"),
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            context_length=context_length,
            capabilities=list(data.get("capabilities") or []),
            default_parameters=_parse_parameters(data.get("parameters") or ""),
            template=data.get("template"),
            # drop huge token tables; keep the architecture numbers
            model_info={k: v for k, v in info.items() if not isinstance(v, list)},
        )

    # ------------------------------------------------------------------ generation
    def generate(self, req: GenerateRequest) -> GenerateResponse:
        body = self._base_body(req.model, req.options, req.think)
        body["prompt"] = req.prompt
        if req.system:
            body["system"] = req.system
        if req.format is not None:
            body["format"] = req.format
        data = self.client.generate(body)
        return GenerateResponse(
            model=data.get("model", body["model"]),
            response=data.get("response", ""),
            thinking=data.get("thinking"),
            done_reason=data.get("done_reason"),
            metrics=metrics_from(data),
        )

    def chat(self, req: ChatRequest) -> ChatResponse:
        body = self._base_body(req.model, req.options, req.think)
        body["messages"] = [m.model_dump() for m in req.messages]
        if req.format is not None:
            body["format"] = req.format
        data = self.client.chat(body)
        message = data.get("message") or {}
        return ChatResponse(
            model=data.get("model", body["model"]),
            message=ChatMessage(role="assistant", content=message.get("content", "")),
            thinking=message.get("thinking"),
            done_reason=data.get("done_reason"),
            metrics=metrics_from(data),
        )

    def warmup(self) -> GenerationMetrics:
        """Load the chat model into memory (an empty prompt only loads it)."""
        data = self.client.generate(
            {
                "model": self.settings.llm_chat_model,
                "prompt": "",
                "keep_alive": self.settings.llm_keep_alive,
            }
        )
        return metrics_from(data)

    # ------------------------------------------------------------------ embeddings
    def embed(self, inputs: list[str], model: str | None = None) -> EmbedResponse:
        name = model or self.settings.llm_embed_model
        vectors = self.client.embed(name, inputs, keep_alive=self.settings.llm_keep_alive)
        return EmbedResponse(
            model=name, dimensions=len(vectors[0]) if vectors else 0, embeddings=vectors
        )

    def similarity(
        self, query: str, candidates: list[str], model: str | None = None
    ) -> SimilarityResponse:
        """Rank candidates by cosine similarity to the query.

        One batched embedding call for query + all candidates, then O(n * d) math
        (n candidates, d dimensions) and an O(n log n) sort.
        """
        name = model or self.settings.llm_embed_model
        vectors = self.client.embed(
            name, [query, *candidates], keep_alive=self.settings.llm_keep_alive
        )
        if len(vectors) != len(candidates) + 1:
            raise UpstreamError("Embedding count mismatch from Ollama.")
        q = vectors[0]
        q_norm = _norm(q)
        scored = (
            SimilarityHit(text=text, score=round(cosine(q, vec, q_norm), 4))
            for text, vec in zip(candidates, vectors[1:], strict=True)
        )
        ranked = sorted(scored, key=lambda h: h.score, reverse=True)
        return SimilarityResponse(model=name, results=ranked)

    # ------------------------------------------------------------------ structured extraction
    def extract_job(self, req: JobExtractionRequest) -> JobExtractionResponse:
        text = req.text
        limit = self.settings.llm_max_input_chars
        truncated = len(text) > limit
        if truncated:
            text = text[:limit]

        body = self._base_body(req.model, req.options, req.think)
        body["messages"] = [
            {"role": "system", "content": prompts.JOB_EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": prompts.JOB_EXTRACTION_USER.format(posting=prompts.fence(text)),
            },
        ]
        # Constrained decoding: Ollama only lets the model emit tokens that keep the
        # output valid against this JSON Schema.
        body["format"] = llm_schema(JobFacts)
        # Hard cap on output length: a normal answer is ~300 tokens. If the model ever
        # loops, it stops here (done_reason="length") instead of running for minutes.
        body["options"].setdefault("num_predict", EXTRACTION_MAX_TOKENS)
        data = self.client.chat(body)
        content = (data.get("message") or {}).get("content", "")
        if data.get("done_reason") == "length":
            raise UpstreamError(
                "The model hit the output limit (likely a repetition loop); result discarded.",
                details={"output_tokens": data.get("eval_count"), "raw_tail": content[-500:]},
            )
        try:
            facts = JobFacts.model_validate_json(content)
        except ValidationError as exc:
            raise UpstreamError(
                "The model returned output that does not match the schema.",
                details={"raw": content[:2000]},
            ) from exc

        clean_job_facts(facts)
        return JobExtractionResponse(
            model=data.get("model", body["model"]),
            prompt_version=prompts.JOB_EXTRACTION_VERSION,
            facts=facts,
            input_truncated=truncated,
            metrics=metrics_from(data),
        )


# ---------------------------------------------------------------------- pure helpers


def metrics_from(data: dict[str, Any]) -> GenerationMetrics:
    def ms(key: str) -> float:
        return round(float(data.get(key, 0)) / 1e6, 1)

    def rate(count: int, duration_ns: float) -> float | None:
        return round(count / (duration_ns / 1e9), 1) if duration_ns > 0 and count > 0 else None

    prompt_tokens = int(data.get("prompt_eval_count", 0))
    output_tokens = int(data.get("eval_count", 0))
    return GenerationMetrics(
        total_ms=ms("total_duration"),
        load_ms=ms("load_duration"),
        prompt_tokens=prompt_tokens,
        prompt_ms=ms("prompt_eval_duration"),
        prompt_tokens_per_s=rate(prompt_tokens, float(data.get("prompt_eval_duration", 0))),
        output_tokens=output_tokens,
        output_ms=ms("eval_duration"),
        output_tokens_per_s=rate(output_tokens, float(data.get("eval_duration", 0))),
    )


# Deterministic safety net behind the prompt: words the model sometimes lists as
# "skills" although they are degree subjects, soft skills or filler.
NON_SKILLS = frozenset(
    {
        "computer science", "mathematics", "math", "statistics", "engineering", "physics",
        "information systems", "information technology", "electrical engineering",
        "programming", "coding", "software engineering", "software development", "technology",
        "communication", "communication skills", "teamwork", "collaboration", "problem solving",
        "problem-solving", "leadership", "curiosity", "ownership", "attention to detail",
        "analytical skills", "written communication", "verbal communication", "english",
    }
)  # fmt: skip


def clean_job_facts(facts: JobFacts) -> None:
    """Normalize + de-duplicate skills, drop non-skills, move degree subjects. O(n)."""
    facts.education_fields = unique_preserving_order(map(normalize_skill, facts.education_fields))
    blocked = NON_SKILLS | set(facts.education_fields)
    facts.required_skills = [
        s
        for s in unique_preserving_order(map(normalize_skill, facts.required_skills))
        if s not in blocked
    ]
    required = set(facts.required_skills)
    facts.preferred_skills = [
        s
        for s in unique_preserving_order(map(normalize_skill, facts.preferred_skills))
        if s not in required and s not in blocked
    ]


def _norm(v: list[float]) -> float:
    return math.sqrt(math.fsum(x * x for x in v))


def cosine(a: list[float], b: list[float], a_norm: float | None = None) -> float:
    """cos(theta) = (a . b) / (|a| |b|). O(d)."""
    denominator = (a_norm if a_norm is not None else _norm(a)) * _norm(b)
    if denominator == 0:
        return 0.0
    return math.fsum(x * y for x, y in zip(a, b, strict=True)) / denominator


def _parse_parameters(raw: str) -> dict[str, str]:
    """Ollama returns Modelfile PARAMETER lines as text: 'temperature 1\\ntop_k 64'."""
    params: dict[str, str] = {}
    for line in raw.splitlines():
        key, _, value = line.strip().partition(" ")
        if key:
            value = value.strip().strip('"')
            params[key] = (
                f"{params[key]}, {value}" if key in params else value
            )  # e.g. multiple stops
    return params
