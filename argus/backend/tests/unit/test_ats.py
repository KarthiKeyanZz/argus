from __future__ import annotations

import pytest

from app.modules.companies.ats import AtsBoard, detect_ats


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/Stripe", AtsBoard("greenhouse", "stripe")),
        ("https://job-boards.greenhouse.io/stripe/jobs/123", AtsBoard("greenhouse", "stripe")),
        ("https://boards.greenhouse.io/embed/job_board?for=acme", AtsBoard("greenhouse", "acme")),
        ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", AtsBoard("greenhouse", "acme")),
        ("https://jobs.lever.co/palantir/abc-123/apply", AtsBoard("lever", "palantir")),
        ("https://api.lever.co/v0/postings/palantir?mode=json", AtsBoard("lever", "palantir")),
        ("https://jobs.ashbyhq.com/ramp", AtsBoard("ashby", "ramp")),
        ("https://api.ashbyhq.com/posting-api/job-board/ramp", AtsBoard("ashby", "ramp")),
        ("https://jobs.smartrecruiters.com/Visa1", AtsBoard("smartrecruiters", "visa1")),
    ],
)
def test_detects_supported_boards(url: str, expected: AtsBoard) -> None:
    assert detect_ats(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://careers.example.com/jobs",
        "https://jobs.lever.co/",
        "https://boards.greenhouse.io/embed/job_board",
        "https://boards-api.greenhouse.io/v1",
        "not a url",
    ],
)
def test_unknown_or_incomplete_urls(url: str) -> None:
    assert detect_ats(url) is None
