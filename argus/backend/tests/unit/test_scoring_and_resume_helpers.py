"""Pure-function tests: fit scoring, date arithmetic, upload safety."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.exceptions import UnprocessableError
from app.modules.matching.scoring import (
    JobInput,
    Prefs,
    SkillHit,
    experience_component,
    freshness_component,
    hard_filter_reasons,
    score_job,
    title_component,
)
from app.modules.resume import files
from app.modules.resume.dates import months_between, parse_month_year

NOW = datetime(2026, 11, 13, tzinfo=UTC)


def _job(**kw: object) -> JobInput:
    base: dict[str, object] = {
        "title": "Software Engineer Intern", "company_name": "Acme", "location_text": "Chennai",
        "work_mode": "onsite", "first_seen_at": NOW, "posted_at": None, "min_years": None,
        "max_years": None, "seniority": "intern", "entry_level_friendly": True,
        "extracted_work_mode": None,
    }  # fmt: skip
    base.update(kw)
    return JobInput(**base)  # type: ignore[arg-type]


def _prefs(**row: object) -> Prefs:
    return Prefs.from_row({"work_modes": ["onsite", "hybrid"], **row})


# ----------------------------------------------------------------------------- skills


def test_skill_hit_statuses_and_credit() -> None:
    assert SkillHit("python", True, "python", 1.0).status == "exact"
    similar = SkillHit("data structures", False, "data structures and algorithms", 0.93)
    assert similar.status == "similar"
    assert similar.credit == pytest.approx(0.93)
    related = SkillHit("java", False, "javascript", 0.65)
    assert related.status == "related"
    assert related.credit == 0
    assert SkillHit("go", False, "python", 0.4).status == "missing"
    assert SkillHit("go", False, None, None).status == "missing"


# ----------------------------------------------------------------------------- components


def test_title_component_maps_calibrated_range() -> None:
    assert title_component(0.45) == 0
    assert title_component(0.75) == 1
    assert title_component(0.60) == pytest.approx(0.5)
    assert title_component(None) is None


def test_experience_component() -> None:
    assert experience_component(_job(min_years=1.0), 2)[0] == 1.0
    assert experience_component(_job(min_years=5.0), 2)[0] == 0.0
    assert experience_component(_job(entry_level_friendly=True), 2)[0] == 1.0
    assert experience_component(_job(entry_level_friendly=False, seniority="senior"), 2)[0] == 0.2


def test_freshness_decays() -> None:
    assert freshness_component(_job(first_seen_at=NOW - timedelta(days=3)), NOW) == 1.0
    assert freshness_component(_job(first_seen_at=NOW - timedelta(days=60)), NOW) == pytest.approx(
        0.2
    )


def test_hard_filters() -> None:
    prefs = _prefs(
        excluded_companies=["Evil Corp Ltd"],
        excluded_keywords=["senior"],
        hard_filters={"max_required_years": 2},
    )
    assert hard_filter_reasons(_job(), prefs) == []
    assert "requires 5+ years" in hard_filter_reasons(_job(min_years=5.0), prefs)[0]
    assert "work mode 'remote'" in hard_filter_reasons(_job(work_mode="remote"), prefs)[0]
    assert "excluded list" in hard_filter_reasons(_job(company_name="EVIL CORP"), prefs)[0]
    assert (
        "excluded keyword 'senior'"
        in hard_filter_reasons(_job(title="Senior Backend Engineer"), prefs)[0]
    )
    # keyword matching is word-based: 'seniority' must not trigger 'senior'
    assert hard_filter_reasons(_job(title="Engineer (no seniority required)"), prefs) == []


def test_score_is_explainable_and_hard_fail_is_not_hidden() -> None:
    required = [
        SkillHit("python", True, "python", 1.0),
        SkillHit("data structures", False, "data structures and algorithms", 0.93),
        SkillHit("go", False, "python", 0.45),
    ]
    good = score_job(_job(required=required, title_similarity=0.75), _prefs(), NOW)
    assert good.passed_hard_filters
    assert 60 < good.score <= 100
    skills = {s["skill"]: s["status"] for s in good.breakdown["skills"]["required"]}
    assert skills == {"python": "exact", "data structures": "similar", "go": "missing"}
    assert good.breakdown["components"]["required_skills"] == pytest.approx((1 + 0.93) / 3, 1e-3)

    bad = score_job(_job(required=required, title_similarity=0.75, min_years=8.0), _prefs(), NOW)
    assert not bad.passed_hard_filters
    assert bad.hard_fail_reasons
    assert bad.score < good.score


def test_unknown_components_are_neutral_not_zero() -> None:
    result = score_job(_job(), _prefs(), NOW)  # no skills listed, no title similarity
    assert set(result.breakdown["unknown_components"]) >= {"required_skills", "title"}
    assert result.breakdown["components"]["required_skills"] == 0.5


def test_weights_are_normalized() -> None:
    result = score_job(_job(), _prefs(scoring_weights={"title": 2, "freshness": 0}), NOW)
    assert sum(result.breakdown["weights"].values()) == pytest.approx(1.0, abs=1e-2)


# ----------------------------------------------------------------------------- dates


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Jun 2025", date(2025, 6, 1)), ("2024", date(2024, 1, 1)), ("June 2025", date(2025, 6, 1)),
     ("nonsense", None), ("", None), (None, None)],
)  # fmt: skip
def test_parse_month_year(text: str | None, expected: date | None) -> None:
    assert parse_month_year(text) == expected


def test_present_and_month_arithmetic() -> None:
    assert parse_month_year("Present", today=date(2026, 11, 13)) == date(2026, 11, 1)
    assert months_between(date(2025, 6, 1), date(2025, 8, 1)) == 3
    assert months_between(date(2024, 11, 1), date(2025, 2, 1)) == 4
    assert months_between(date(2025, 8, 1), date(2025, 6, 1)) is None


# ----------------------------------------------------------------------------- uploads


def make_docx(text: str) -> bytes:
    import docx

    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_pdf(text: str) -> bytes:
    """Minimal valid single-page PDF with one line of text (no extra dependencies)."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return out.getvalue()


LONG_TEXT = "Alex Example - Python developer with FastAPI, PostgreSQL and Docker experience."


def test_parse_docx_and_pdf() -> None:
    docx_file = files.parse_upload(make_docx(LONG_TEXT + "\nSkills: Python"))
    assert docx_file.kind == "docx"
    assert "FastAPI" in docx_file.text
    pdf_file = files.parse_upload(make_pdf(LONG_TEXT))
    assert pdf_file.kind == "pdf"
    assert "PostgreSQL" in pdf_file.text


def test_rejects_wrong_type_empty_and_oversized() -> None:
    with pytest.raises(UnprocessableError, match="Unsupported"):
        files.parse_upload(b"#!/bin/sh\nrm -rf /\n" * 10)
    with pytest.raises(UnprocessableError, match="empty"):
        files.parse_upload(b"")
    with pytest.raises(UnprocessableError, match="5 MB"):
        files.parse_upload(b"%PDF-" + b"0" * files.MAX_UPLOAD_BYTES)


def test_rejects_zip_that_is_not_docx_and_macro_documents() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("evil.txt", "x")
    with pytest.raises(UnprocessableError, match="not a Word document"):
        files.parse_upload(buffer.getvalue())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", "<x/>")
        z.writestr("word/vbaProject.bin", "macro")
    with pytest.raises(UnprocessableError, match="macros"):
        files.parse_upload(buffer.getvalue())


def test_store_uses_random_names_and_private_permissions(tmp_path: object) -> None:
    from pathlib import Path

    folder = Path(str(tmp_path))
    name = files.store(folder, "pdf", b"%PDF-1.4 test")
    path = folder / "resumes" / name
    assert path.read_bytes() == b"%PDF-1.4 test"
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    files.remove(folder, "../../etc/passwd")  # refused, no exception
    files.remove(folder, name)
    assert not path.exists()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("linkedin.com/in/x", "https://linkedin.com/in/x"), ("https://github.com/x", "https://github.com/x"),
     ("javascript:alert(1)", None), ("ftp://x.org", None), ("not a url", None), (None, None)],
)  # fmt: skip
def test_with_scheme(raw: str | None, expected: str | None) -> None:
    from app.modules.resume.service import with_scheme

    assert with_scheme(raw) == expected
