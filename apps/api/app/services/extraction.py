"""Document → structured invoice extraction.

Pulls text from PDFs/Word/Excel/CSV and hands the document to the AI provider for
structured extraction. Scanned PDFs and images are passed as raw bytes so the
provider can OCR them natively (Claude document/vision input). Parsing libraries are
optional imports — the pipeline degrades to AI-only extraction if a parser is absent.

Returns a list of (source_label, Invoice) so a single upload (or ZIP) can yield
multiple invoices.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field

from ..ai.base import ExtractionInput
from ..ai.factory import get_ai_provider
from ..vat.schemas import Invoice
from . import ocr

_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff", ".bmp")
_SUPPORTED_EXT = (".pdf", ".docx", ".xlsx", ".csv", ".txt", ".zip", *_IMAGE_EXT)


class UnsupportedFileError(ValueError):
    """Raised when an uploaded file's type is not supported."""


@dataclass
class ExtractedDoc:
    label: str
    invoice: Invoice
    raw_text: str = ""
    ocr_used: bool = False
    ocr_engine: str | None = None
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _pdf_text(data: bytes) -> str:
    return ocr.extract_pdf_text(data).text


def _docx_text(data: bytes) -> str:
    try:
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs).strip()
    except Exception:  # noqa: BLE001
        return ""


def _xlsx_text(data: bytes) -> str:
    try:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        lines: list[str] = []
        for ws in wb.worksheets:
            lines.append(f"# Sheet: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                cells = ["" if c is None else str(c) for c in row]
                if any(cells):
                    lines.append("\t".join(cells))
        return "\n".join(lines).strip()
    except Exception:  # noqa: BLE001
        return ""


def _csv_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        return "\n".join("\t".join(r) for r in rows).strip()
    except Exception:  # noqa: BLE001
        return ""


def _read_text(filename: str, data: bytes) -> ocr.TextExtraction:
    """Get raw text (with OCR where needed) and extraction metadata for a file."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return ocr.extract_pdf_text(data)
    if lower.endswith(_IMAGE_EXT):
        return ocr.extract_image_text(data)
    if lower.endswith(".docx"):
        return ocr.TextExtraction(text=_docx_text(data), page_count=1)
    if lower.endswith(".xlsx"):
        return ocr.TextExtraction(text=_xlsx_text(data), page_count=1)
    if lower.endswith(".csv"):
        return ocr.TextExtraction(text=_csv_text(data), page_count=1)
    if lower.endswith(".txt"):
        return ocr.TextExtraction(text=data.decode("utf-8", errors="replace"), page_count=1)
    raise UnsupportedFileError(f"Unsupported file type: {filename}")


def _build_input(filename: str, data: bytes, mime: str | None, text: str | None) -> ExtractionInput:
    # Raw document bytes are attached for PDFs/images so an AI provider can use native
    # document/vision input; other formats pass their extracted text only.
    lower = filename.lower()
    doc_bytes = data if lower.endswith((".pdf", *_IMAGE_EXT)) else None
    return ExtractionInput(filename=filename, mime=mime, text=text or None, doc_bytes=doc_bytes)


def _extract_one(filename: str, data: bytes, mime: str | None) -> ExtractedDoc:
    te = _read_text(filename, data)
    provider = get_ai_provider()
    source = _build_input(filename, data, mime, te.text)
    invoice = provider.extract_invoice(source)
    return ExtractedDoc(
        label=filename,
        invoice=invoice,
        raw_text=te.text,
        ocr_used=te.ocr_used,
        ocr_engine=te.engine,
        page_count=te.page_count,
        warnings=list(te.warnings),
    )


def document_text(filename: str, data: bytes) -> str:
    """Extract plain text from a document for knowledge-base ingestion."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _pdf_text(data)
    if lower.endswith(".docx"):
        return _docx_text(data)
    if lower.endswith(".xlsx"):
        return _xlsx_text(data)
    if lower.endswith(".csv"):
        return _csv_text(data)
    return data.decode("utf-8", errors="replace")


def extract_invoices(filename: str, data: bytes, mime: str | None = None) -> list[ExtractedDoc]:
    """Extract one or more invoices from an uploaded file (ZIP -> many)."""
    if filename.lower().endswith(".zip"):
        results: list[ExtractedDoc] = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.filename.startswith("__MACOSX"):
                    continue
                if not info.filename.lower().endswith(_SUPPORTED_EXT):
                    continue  # skip unsupported entries silently within a batch
                inner = zf.read(info)
                try:
                    results.append(_extract_one(info.filename, inner, None))
                except UnsupportedFileError:
                    continue
        if not results:
            raise UnsupportedFileError("ZIP contained no supported documents.")
        return results

    return [_extract_one(filename, data, mime)]
