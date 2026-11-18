"""Pure-ASGI middlewares (cheaper than BaseHTTPMiddleware, streaming-safe).

* ``RequestContextMiddleware`` - request id, timing header, one access-log line.
* ``OriginGuardMiddleware``   - blocks cross-site state-changing requests (CSRF).

ARGUS binds to 127.0.0.1 only, but a malicious web page open in your browser can
still send requests to localhost. Browsers always attach an ``Origin`` header to
cross-origin POST/PUT/PATCH/DELETE, so rejecting unknown origins stops that.
Requests without ``Origin`` (curl, tests, the worker) are allowed.
DNS-rebinding is handled separately by Starlette's ``TrustedHostMiddleware``.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Iterable

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import error_body
from app.core.logging import request_id_ctx

logger = logging.getLogger("argus.access")

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                elapsed_ms = (time.perf_counter() - started) * 1000
                headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %d (%.1f ms)", scope["method"], scope["path"], status_code, elapsed_ms
            )
            request_id_ctx.reset(token)


class OriginGuardMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed = frozenset(o.rstrip("/").lower() for o in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in _SAFE_METHODS:
            origin = Headers(scope=scope).get("origin")
            if origin is not None and origin.rstrip("/").lower() not in self.allowed:
                body = json.dumps(
                    error_body("forbidden_origin", "Cross-origin request blocked.")
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
