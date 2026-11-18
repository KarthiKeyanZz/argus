from __future__ import annotations

import logging

from app.core.logging import RedactingFormatter, redact


def test_redacts_emails_phones_tokens_and_url_credentials() -> None:
    text = (
        "user jane.doe@example.com phone +91 98765 43210 alt 9876543210 "
        "Authorization: Bearer abc.def-123 password=hunter2 otp: 482913 "
        "dsn postgresql://argus:s3cret@127.0.0.1:5433/argus"
    )
    out = redact(text)
    for secret in (
        "jane.doe@example.com",
        "98765 43210",
        "9876543210",
        "abc.def-123",
        "hunter2",
        "482913",
        "s3cret",
    ):
        assert secret not in out
    assert "postgresql://[credentials]@127.0.0.1:5433/argus" in out


def test_does_not_mangle_ordinary_numbers() -> None:
    text = "2026-11-13 took 1234 ms, job 42, status 200"
    assert redact(text) == text


def test_formatter_redacts_tracebacks() -> None:
    formatter = RedactingFormatter("%(message)s")
    try:
        raise ValueError("bad email someone@example.org")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    assert "someone@example.org" not in formatter.format(record)
