"""Detect which applicant-tracking system (ATS) hosts a careers page.

Paste ``https://jobs.lever.co/acme`` -> ``("lever", "acme")``. The token is
what the ATS public API needs to list that company's jobs. Lookup is a dict
keyed by hostname, so detection is O(1) in the number of supported ATSs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

AtsKind = Literal["greenhouse", "lever", "ashby", "smartrecruiters"]


@dataclass(frozen=True, slots=True)
class AtsBoard:
    kind: AtsKind
    token: str


# hostname -> (kind, index of the path segment holding the token)
_HOSTS: dict[str, tuple[AtsKind, int]] = {
    "boards.greenhouse.io": ("greenhouse", 0),
    "job-boards.greenhouse.io": ("greenhouse", 0),
    "job-boards.eu.greenhouse.io": ("greenhouse", 0),
    "boards.eu.greenhouse.io": ("greenhouse", 0),
    "boards-api.greenhouse.io": ("greenhouse", 2),  # /v1/boards/{token}/...
    "jobs.lever.co": ("lever", 0),
    "jobs.eu.lever.co": ("lever", 0),
    "api.lever.co": ("lever", 2),  # /v0/postings/{token}
    "jobs.ashbyhq.com": ("ashby", 0),
    "api.ashbyhq.com": ("ashby", 2),  # /posting-api/job-board/{token}
    "jobs.smartrecruiters.com": ("smartrecruiters", 0),
    "careers.smartrecruiters.com": ("smartrecruiters", 0),
}

_RESERVED_FIRST_SEGMENTS = frozenset({"embed", "v1", "jobs", "api"})


def detect_ats(url: str) -> AtsBoard | None:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    match = _HOSTS.get(host)
    if match is None:
        return None
    kind, index = match

    # Greenhouse embed form: boards.greenhouse.io/embed/job_board?for=acme
    if kind == "greenhouse" and parts.path.startswith("/embed"):
        token = parse_qs(parts.query).get("for", [""])[0]
        return AtsBoard(kind, token.lower()) if token else None

    segments = [s for s in parts.path.split("/") if s]
    if len(segments) <= index:
        return None
    token = segments[index].lower()
    if index == 0 and token in _RESERVED_FIRST_SEGMENTS:
        return None
    return AtsBoard(kind, token)
