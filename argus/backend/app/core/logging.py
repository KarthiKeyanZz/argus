"""Logging setup with request-id correlation and PII/secret redaction.

Redaction runs in the *formatter*, so it also covers exception tracebacks.
All patterns are linear-time regexes (no nested quantifiers -> no ReDoS).
"""

from __future__ import annotations

import logging
import logging.config
import re
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # credentials embedded in connection URLs: scheme://user:pass@host
    (
        re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^\s:/@]+:[^\s/@]+@", re.IGNORECASE),
        r"\1[credentials]@",
    ),
    # Authorization: Bearer xxx
    (re.compile(r"\b(bearer)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), r"\1 [token]"),
    # key=value / key: value for secret-ish keys
    (
        re.compile(
            r"\b(password|passwd|secret|token|api[_-]?key|client[_-]?secret|otp|access[_-]?code)"
            r"(\"?\s*[:=]\s*\"?)([^\s\",}]+)",
            re.IGNORECASE,
        ),
        r"\1\2[redacted]",
    ),
    # e-mail addresses
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    # international phone numbers (+CC ...) and bare 10-digit mobile numbers
    (re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?\d{2,5}[\s.-]?\d{3,5}[\s.-]?\d{0,5}(?!\w)"), "[phone]"),
    (re.compile(r"(?<![\w.-])\d{10}(?![\w.-])"), "[phone]"),
)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "default": {
                    "()": RedactingFormatter,
                    "format": "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                }
            },
            "root": {"level": level, "handlers": ["console"]},
            "loggers": {
                # route uvicorn through our redacting handler
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                "uvicorn.access": {"handlers": [], "propagate": False},  # we log requests ourselves
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
            },
        }
    )
