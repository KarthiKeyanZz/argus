from __future__ import annotations

import pytest

from app.shared.text import (
    canonical_url,
    company_key,
    escape_like,
    job_dedupe_key,
    normalize_question,
    normalize_skill,
    unique_preserving_order,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Acme Technologies Pvt. Ltd.", "acme"),
        ("ACME Inc", "acme"),
        ("  Stripe, Inc. ", "stripe"),
        ("Company Inc", "company"),  # never strips the last remaining token
        ("Tata Consultancy Services Limited", "tata-consultancy-services"),
        ("Zoho Corporation Private Limited", "zoho"),
    ],
)
def test_company_key(name: str, expected: str) -> None:
    assert company_key(name) == expected


def test_canonical_url_strips_tracking_and_fragment() -> None:
    url = "HTTPS://Jobs.Lever.co:443/acme/123/?utm_source=x&lever-source=li&b=2&a=1#apply"
    assert canonical_url(url) == "https://jobs.lever.co/acme/123?a=1&b=2"


def test_canonical_url_keeps_non_default_port() -> None:
    assert canonical_url("http://localhost:8080/x/") == "http://localhost:8080/x"


def test_dedupe_key_ignores_case_whitespace_and_legal_suffix() -> None:
    a = job_dedupe_key("Acme Inc.", "Junior  Engineer", "Bengaluru")
    b = job_dedupe_key("acme", "junior engineer", " bengaluru ")
    assert a == b
    assert len(a) == 40


def test_normalizers() -> None:
    assert normalize_skill("  PostgreSQL. ") == "postgresql"
    assert normalize_question("Are you authorized to work in India? *") == (
        "are you authorized to work in india"
    )


def test_unique_preserving_order() -> None:
    assert unique_preserving_order(["b", "a", "b", "", "c", "a"]) == ["b", "a", "c"]


def test_escape_like() -> None:
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"
