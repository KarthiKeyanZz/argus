"""FastAPI application factory.

Run:  make api   ->  http://127.0.0.1:8000/docs (Swagger UI)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import OriginGuardMiddleware, RequestContextMiddleware
from app.core.openapi import DESCRIPTION, SWAGGER_UI_PARAMETERS, TAGS, operation_id
from app.db.pool import Database
from app.modules.llm.client import OllamaClient
from app.modules.llm.service import LLMService

logger = logging.getLogger("argus")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        app.state.settings = settings
        app.state.db = Database.from_settings(settings)
        client = OllamaClient(settings.ollama_base_url, timeout_s=settings.llm_request_timeout_s)
        app.state.llm = LLMService(client, settings)
        logger.info("ARGUS API %s started (%s)", __version__, settings.environment)
        try:
            yield
        finally:
            client.close()
            app.state.db.close()
            logger.info("ARGUS API stopped")

    app = FastAPI(
        title="ARGUS API",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
        generate_unique_id_function=operation_id,
        lifespan=lifespan,
    )

    # Middleware order: the LAST added runs FIRST (outermost).
    app.add_middleware(
        OriginGuardMiddleware, allowed_origins=[*settings.cors_origins, *settings.self_origins]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Server-Timing"],
        max_age=600,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    return app


app = create_app()
