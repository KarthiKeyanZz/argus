"""OpenAPI / Swagger metadata."""

from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute

DESCRIPTION = """
**ARGUS** - local-first job discovery, matching and application assistant.

* Everything runs on your machine: PostgreSQL, the API, the worker and the LLM (Ollama).
* Swagger UI (this page): `/docs` · ReDoc: `/redoc` · OpenAPI JSON: `/openapi.json`.
* Long-running work (LLM extraction, discovery, applying) runs in the **worker**
  (`make worker`) and is tracked under **tasks**.
* Errors always use the envelope `{"error": {"code", "message", "details", "request_id"}}`.
* Lists use **cursor pagination**: pass `next_cursor` back as `cursor`.
"""

TAGS: list[dict[str, Any]] = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "profile", "description": "Your verified career profile and skills."},
    {"name": "resume", "description": "Upload, parse (local LLM), review and import resumes."},
    {"name": "preferences", "description": "What jobs you want, scoring weights, hard filters."},
    {"name": "companies", "description": "Companies to watch and their ATS job boards."},
    {"name": "jobs", "description": "Discovered and manually added job postings."},
    {
        "name": "matching",
        "description": "Explainable fit scores: semantic skill matching (pgvector), "
        "weights and hard filters from your preferences.",
    },
    {
        "name": "llm",
        "description": "Local LLM playground and building blocks (Ollama). Each response "
        "includes timing metrics so you can see the effect of tuning parameters.",
    },
    {"name": "tasks", "description": "Background task queue processed by the worker."},
    {"name": "system", "description": "Global pause / resume (kill switch)."},
    {"name": "audit", "description": "Append-only trail of every consequential action."},
]

SWAGGER_UI_PARAMETERS: dict[str, Any] = {
    "displayRequestDuration": True,
    "filter": True,
    "tryItOutEnabled": True,
    "defaultModelsExpandDepth": 0,
    "docExpansion": "list",
    "persistAuthorization": False,
}


def operation_id(route: APIRoute) -> str:
    """Stable, readable operation ids (e.g. `jobs-list_jobs`) for generated TS clients."""
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"
