"""Text normalization helpers. All functions are O(len(input))."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Legal-entity suffixes stripped from company names when building a stable key.
_COMPANY_SUFFIXES = frozenset(
    {
        "inc", "incorporated", "llc", "ltd", "limited", "pvt", "private", "plc", "corp",
        "corporation", "co", "company", "gmbh", "ag", "sa", "bv", "nv", "srl", "pte", "pty",
        "llp", "lp", "oy", "ab", "as", "kk", "technologies", "technology",
    }
)  # fmt: skip

# Query parameters that only track where a click came from.
_TRACKING_PARAMS = frozenset(
    {
        "gh_src", "gh_jid_src", "lever-source", "lever-origin", "source", "src", "ref",
        "referrer", "trk", "trackingid", "fbclid", "gclid", "mc_cid", "mc_eid",
    }
)  # fmt: skip


def normalize_text(value: str) -> str:
    """NFKC, lowercase, single spaces, trimmed."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", value)).strip().lower()


def normalize_skill(value: str) -> str:
    return normalize_text(value).strip(" .,;:")


def normalize_question(value: str) -> str:
    return normalize_text(value).rstrip(" ?*:")


def company_key(name: str) -> str:
    """'Acme Technologies Pvt. Ltd.' -> 'acme'. Stable key for de-duplication."""
    tokens = _NON_ALNUM.sub(" ", normalize_text(name)).split()
    # strip suffix tokens from the end only ('Company Inc' keeps 'company')
    while len(tokens) > 1 and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return "-".join(tokens)


def canonical_url(url: str) -> str:
    """Lowercase scheme/host, drop fragment, tracking params, default port, trailing slash."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=False)
            if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
        )
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, host, path, query, ""))


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def job_dedupe_key(company: str, title: str, location: str | None) -> str:
    """Cross-source duplicate key: same company + title + location => same job."""
    basis = "|".join((company_key(company), normalize_text(title), normalize_text(location or "")))
    return hashlib.sha1(basis.encode("utf-8"), usedforsecurity=False).hexdigest()


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    """Drop duplicates in O(n) while keeping first-seen order."""
    return list(dict.fromkeys(v for v in values if v))


def escape_like(value: str) -> str:
    """Escape LIKE/ILIKE wildcards so user input is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
