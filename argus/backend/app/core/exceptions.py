"""Domain exceptions and their mapping to a single JSON error envelope.

Every error response looks like::

    {"error": {"code": "not_found", "message": "...", "details": {...}, "request_id": "..."}}
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import request_id_ctx

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnprocessableError(AppError):
    status_code = 422
    code = "unprocessable"


class SystemPausedError(AppError):
    status_code = 423
    code = "system_paused"


class UpstreamError(AppError):
    """A dependency (e.g. Ollama) answered, but with an error."""

    status_code = 502
    code = "upstream_error"


class ServiceUnavailableError(AppError):
    """A dependency (database, Ollama) is not reachable."""

    status_code = 503
    code = "service_unavailable"


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id_ctx.get(),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(error_body(exc.code, exc.message, exc.details), exc.status_code)

    @app.exception_handler(psycopg2.OperationalError)
    async def _db_down(_: Request, exc: psycopg2.OperationalError) -> JSONResponse:
        logger.error("database operational error: %s", exc)
        return JSONResponse(
            error_body("database_unavailable", "The database is not reachable."), 503
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", exc_info=exc)
        return JSONResponse(error_body("internal_error", "Unexpected server error."), 500)
