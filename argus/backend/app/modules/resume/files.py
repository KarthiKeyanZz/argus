"""Safe handling of uploaded resume files.

Uploads are untrusted. We:
* cap the size before reading everything into memory;
* detect the type from the file's *bytes* (magic numbers), never from the name;
* reject DOCX zip-bombs (too many entries / huge uncompressed size);
* store under a random name inside data_dir with 0600 permissions (no path traversal);
* only *read text* out of the file - nothing in it is executed (no macros, no scripts).
"""

from __future__ import annotations

import io
import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.exceptions import UnprocessableError

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 12
MAX_TEXT_CHARS = 60_000
_MAX_ZIP_ENTRIES = 2_000
_MAX_ZIP_UNCOMPRESSED = 60 * 1024 * 1024

Kind = Literal["pdf", "docx"]
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True, slots=True)
class ParsedFile:
    kind: Kind
    mime_type: str
    text: str


def detect_kind(data: bytes) -> Kind:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return "docx"
    raise UnprocessableError("Unsupported file type. Upload a PDF or DOCX resume.")


def _docx_guard(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = {i.filename for i in infos}
    except zipfile.BadZipFile as exc:
        raise UnprocessableError("The DOCX file is corrupted.") from exc
    if "word/document.xml" not in names:
        raise UnprocessableError("This ZIP file is not a Word document.")
    if len(infos) > _MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > _MAX_ZIP_UNCOMPRESSED:
        raise UnprocessableError("The DOCX file is suspiciously large when uncompressed.")
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise UnprocessableError("Documents containing macros are not accepted.")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise UnprocessableError("Password-protected PDFs are not supported.")
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((page.extract_text() or "") for page in pages)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise UnprocessableError("Could not read this PDF.") from exc


def _docx_text(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs]
    lines.extend(  # resumes often use tables for layout
        " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
        for table in document.tables
        for row in table.rows
    )
    return "\n".join(lines)


_BLANK_LINES = re.compile(r"\n\s*\n+")
_SPACES = re.compile(r"[ \t\u00a0]+")


def clean_text(text: str) -> str:
    text = _SPACES.sub(" ", text.replace("\r", "\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()[:MAX_TEXT_CHARS]


def parse_upload(data: bytes) -> ParsedFile:
    if not data:
        raise UnprocessableError("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnprocessableError("Resume files must be 5 MB or smaller.")
    kind = detect_kind(data)
    if kind == "docx":
        _docx_guard(data)
        text = _docx_text(data)
    else:
        text = _pdf_text(data)
    text = clean_text(text)
    if len(text) < 50:
        raise UnprocessableError(
            "No readable text found. Scanned/image-only resumes are not supported yet."
        )
    return ParsedFile(kind=kind, mime_type=MIME[kind], text=text)


def store(data_dir: Path, kind: Kind, data: bytes) -> str:
    """Write bytes under a random name; returns the stored file name (not a path)."""
    folder = data_dir / "resumes"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{kind}"
    path = folder / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return name


def remove(data_dir: Path, stored_name: str) -> None:
    # stored_name comes from our DB, but validate anyway: no separators allowed.
    if "/" in stored_name or "\\" in stored_name or stored_name.startswith("."):
        logger.warning("refusing to delete suspicious stored name")
        return
    (data_dir / "resumes" / stored_name).unlink(missing_ok=True)
