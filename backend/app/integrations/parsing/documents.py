"""Upload validation (magic bytes, macros, zip bombs, encryption, page cap) and PDF/DOCX text extraction."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from app.core.errors import FileTooLarge, UnsupportedFileType, ValidationFailed
from app.domain.text import clean_text

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_ENTRIES = 1000
MAX_RATIO = 100


@dataclass
class UploadInfo:
    kind: str
    mime_type: str
    size: int
    page_count: int | None = None


@dataclass
class ParsedDocument:
    text: str
    page_count: int | None
    pages: list[str] = field(default_factory=list)


def _check_docx(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            names = {i.filename for i in infos}
            if len(infos) > MAX_ENTRIES:
                raise ValidationFailed("The document has too many internal parts.")
            total = sum(i.file_size for i in infos)
            compressed = sum(max(1, i.compress_size) for i in infos)
            if total > MAX_UNCOMPRESSED or total / compressed > MAX_RATIO:
                raise ValidationFailed("The document expands to an unsafe size.")
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UnsupportedFileType("This is not a valid DOCX file.")
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise UnsupportedFileType("Macro-enabled documents are not accepted.")
    except zipfile.BadZipFile as exc:
        raise UnsupportedFileType("This is not a valid DOCX file.") from exc


def validate_upload(data: bytes, max_mb: int, max_pages: int) -> UploadInfo:
    if len(data) > max_mb * 1024 * 1024:
        raise FileTooLarge(f"Files must be {max_mb} MB or smaller.")
    if not data:
        raise ValidationFailed("The file is empty.")
    if data[:5] == b"%PDF-":
        import pymupdf

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:  # pymupdf raises its own error types
            raise UnsupportedFileType("This PDF could not be read.") from exc
        try:
            if doc.needs_pass or doc.is_encrypted:
                raise ValidationFailed("Encrypted PDFs are not supported. Remove the password and try again.")
            if doc.page_count > max_pages:
                raise ValidationFailed(f"PDFs may have at most {max_pages} pages.")
            return UploadInfo("pdf", PDF_MIME, len(data), doc.page_count)
        finally:
            doc.close()
    if data[:4] == b"PK\x03\x04":
        _check_docx(data)
        return UploadInfo("docx", DOCX_MIME, len(data))
    raise UnsupportedFileType()


def extract_document(data: bytes, kind: str) -> ParsedDocument:
    if kind == "pdf":
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages = [page.get_text("text", sort=True) for page in doc]
        return ParsedDocument(text=clean_text("\n".join(pages)), page_count=len(pages), pages=[clean_text(p) for p in pages])
    if kind == "docx":
        import docx

        document = docx.Document(io.BytesIO(data))
        lines: list[str] = []
        for para in document.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name or "").lower() if para.style is not None else ""
            if "list" in style and not text.startswith(("-", "•")):
                text = "- " + text
            lines.append(text)
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    lines.append(" | ".join(dict.fromkeys(cells)))
        return ParsedDocument(text=clean_text("\n".join(lines)), page_count=None)
    raise UnsupportedFileType()
