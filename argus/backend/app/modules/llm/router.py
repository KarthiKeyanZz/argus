"""LLM playground + building blocks. Every endpoint returns timing metrics so you can
see the effect of each tuning knob (see docs/learning/01-llm-fundamentals.md)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import LLMDep
from app.modules.llm.schemas import (
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
    JobExtractionRequest,
    JobExtractionResponse,
    ModelDetails,
    ModelList,
    SimilarityRequest,
    SimilarityResponse,
)
from app.shared.schemas import ERROR_RESPONSES

router = APIRouter(prefix="/llm", tags=["llm"], responses={**ERROR_RESPONSES, 502: {}, 503: {}})


@router.get("/models", response_model=ModelList, summary="Installed and loaded models")
def list_models(llm: LLMDep) -> ModelList:
    return llm.list_models()


@router.get(
    "/models/{name}",
    response_model=ModelDetails,
    summary="Model card: context length, defaults, chat template",
)
def model_details(llm: LLMDep, name: Annotated[str, Path(max_length=200)]) -> ModelDetails:
    return llm.model_details(name)


@router.post("/generate", response_model=GenerateResponse, summary="Raw completion (playground)")
def generate(llm: LLMDep, body: GenerateRequest) -> GenerateResponse:
    return llm.generate(body)


@router.post("/chat", response_model=ChatResponse, summary="Chat completion (playground)")
def chat(llm: LLMDep, body: ChatRequest) -> ChatResponse:
    return llm.chat(body)


@router.post("/embed", response_model=EmbedResponse, summary="Text -> embedding vectors")
def embed(llm: LLMDep, body: EmbedRequest) -> EmbedResponse:
    return llm.embed(body.inputs, body.model)


@router.post(
    "/similarity",
    response_model=SimilarityResponse,
    summary="Semantic search: rank texts by meaning",
)
def similarity(llm: LLMDep, body: SimilarityRequest) -> SimilarityResponse:
    return llm.similarity(body.query, body.candidates, body.model)


@router.post(
    "/extract/job",
    response_model=JobExtractionResponse,
    summary="Extract structured facts from a job posting",
    description="Uses a JSON Schema as `format`, so the model is forced to return exactly the "
    "`JobFacts` shape. The posting is treated as untrusted data (prompt-injection safe).",
)
def extract_job(llm: LLMDep, body: JobExtractionRequest) -> JobExtractionResponse:
    return llm.extract_job(body)
