"""Thin, explicit client for the Ollama REST API (http://127.0.0.1:11434).

We call the HTTP API directly (no SDK) so every request is visible and easy to
learn from. Endpoints used:

    GET  /api/version      server version
    GET  /api/tags         models installed on disk
    GET  /api/ps           models currently loaded in (GPU/CPU) memory
    POST /api/show         model metadata: parameters, template, context length...
    POST /api/generate     single prompt -> completion
    POST /api/chat         list of messages -> next assistant message
    POST /api/embed        texts -> embedding vectors

Docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.exceptions import NotFoundError, ServiceUnavailableError, UpstreamError

logger = logging.getLogger(__name__)


def model_tag(name: str) -> str:
    """Ollama treats 'nomic-embed-text' and 'nomic-embed-text:latest' as the same model."""
    return name if ":" in name else f"{name}:latest"


class OllamaClient:
    def __init__(self, base_url: str, *, timeout_s: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        # Connect fast, but allow long reads: a 16 GB model can take a while to load
        # and generation time grows with output length.
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={"User-Agent": "argus-backend"},
        )

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ low level
    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.ConnectError as exc:
            raise ServiceUnavailableError(
                f"Ollama is not reachable at {self.base_url}. "
                "Start it with: systemctl --user start ollama"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                "Ollama timed out. The model may still be loading or the prompt is too large."
            ) from exc

        if response.status_code == 404:
            model = (json or {}).get("model", "")
            raise NotFoundError(
                f"Model '{model}' is not installed. Download it with: ollama pull {model}",
                details={"model": model},
            )
        if response.is_error:
            message = _error_message(response)
            raise UpstreamError(f"Ollama error ({response.status_code}): {message}")
        return response.json()

    # ------------------------------------------------------------------ endpoints
    def version(self) -> str:
        return str(self._request("GET", "/api/version").get("version", "unknown"))

    def list_models(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/api/tags").get("models", []))

    def running_models(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/api/ps").get("models", []))

    def show(self, model: str) -> dict[str, Any]:
        return dict(self._request("POST", "/api/show", {"model": model}))

    def generate(self, body: dict[str, Any]) -> dict[str, Any]:
        return dict(self._request("POST", "/api/generate", {**body, "stream": False}))

    def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        return dict(self._request("POST", "/api/chat", {**body, "stream": False}))

    def embed(
        self, model: str, inputs: list[str], *, keep_alive: str | None = None
    ) -> list[list[float]]:
        body: dict[str, Any] = {"model": model, "input": inputs, "truncate": True}
        if keep_alive:
            body["keep_alive"] = keep_alive
        data = self._request("POST", "/api/embed", body)
        return [list(map(float, vec)) for vec in data.get("embeddings", [])]


def _error_message(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", response.text))[:500]
    except ValueError:
        return response.text[:500]
