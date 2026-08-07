"""Text extraction with OCR fallback.

Strategy:
- PDFs: extract the embedded text layer with PyMuPDF. Pages with little/no text are
  treated as scanned — rasterised and passed through offline OCR (RapidOCR, ONNX,
  no system binaries, no API key).
- Images: OCR directly.

Everything degrades gracefully: if a library is missing or OCR fails, the caller
still receives whatever text was recoverable plus flags describing what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Pages with fewer than this many characters of embedded text are treated as scanned.
_SCANNED_TEXT_THRESHOLD = 25
_OCR_RENDER_SCALE = 2.0  # 2x → ~144 dpi, a good OCR/perf balance

_ocr_engine = None


@dataclass
class TextExtraction:
    text: str = ""
    page_count: int = 0
    ocr_used: bool = False
    engine: str | None = None
    warnings: list[str] = field(default_factory=list)


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _reconstruct_lines(result) -> str:
    """Rebuild visual lines from OCR text boxes using their coordinates.

    RapidOCR returns detached text boxes; naively joining them loses the spatial
    relationship between a label and its value (e.g. a table cell "Gross Total" and
    the amount in the next column). Grouping boxes by vertical position and ordering
    them left-to-right preserves label↔value adjacency, which the field parser relies
    on. Generic — no per-template coordinates.
    """
    items: list[tuple[float, float, float, str]] = []
    for entry in result:
        try:
            box, text = entry[0], entry[1]
            ys = [float(p[1]) for p in box]
            xs = [float(p[0]) for p in box]
        except Exception:  # noqa: BLE001 — unexpected shape; skip this box
            continue
        y_center = sum(ys) / len(ys)
        items.append((y_center, min(xs), max(ys) - min(ys), str(text)))
    if not items:
        return ""

    items.sort(key=lambda t: (t[0], t[1]))
    heights = sorted(h for _, _, h, _ in items if h > 0)
    median_h = heights[len(heights) // 2] if heights else 12.0
    threshold = max(median_h * 0.6, 6.0)

    lines: list[list[tuple[float, str]]] = []
    current: list[tuple[float, str]] = []
    current_y: float | None = None
    for y_center, x_left, _h, text in items:
        if current_y is None or abs(y_center - current_y) <= threshold:
            current.append((x_left, text))
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            lines.append(current)
            current = [(x_left, text)]
            current_y = y_center
    if current:
        lines.append(current)

    out: list[str] = []
    for line in lines:
        line.sort(key=lambda t: t[0])
        out.append(" ".join(text for _, text in line).strip())
    return "\n".join(ln for ln in out if ln)


def ocr_image_bytes(data: bytes) -> str:
    """OCR raw image bytes (PNG/JPG/…) into layout-aware text. Returns '' on failure."""
    try:
        engine = _get_ocr_engine()
        result, _ = engine(data)
        if not result:
            return ""
        return _reconstruct_lines(result)
    except Exception:  # noqa: BLE001
        return ""


def extract_pdf_text(data: bytes) -> TextExtraction:
    out = TextExtraction()
    try:
        import fitz  # PyMuPDF
    except Exception:  # noqa: BLE001
        out.warnings.append("PyMuPDF not installed; cannot read PDF.")
        return out

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:  # noqa: BLE001
        out.warnings.append("PDF could not be opened (corrupt or password-protected).")
        return out

    out.page_count = doc.page_count
    parts: list[str] = []
    for i, page in enumerate(doc):
        try:
            embedded = (page.get_text() or "").strip()
        except Exception:  # noqa: BLE001
            embedded = ""
        if len(embedded) >= _SCANNED_TEXT_THRESHOLD:
            parts.append(embedded)
            continue
        # Scanned page → rasterise + OCR.
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(_OCR_RENDER_SCALE, _OCR_RENDER_SCALE))
            page_text = ocr_image_bytes(pix.tobytes("png"))
            if page_text:
                out.ocr_used = True
                out.engine = "rapidocr"
                parts.append(page_text)
            else:
                out.warnings.append(f"Page {i + 1}: OCR produced no text (poor scan?).")
        except Exception:  # noqa: BLE001
            out.warnings.append(f"Page {i + 1}: rasterisation/OCR failed.")

    out.text = "\n".join(p for p in parts if p).strip()
    if not out.text:
        out.warnings.append("No text could be extracted from this document.")
    return out


def extract_image_text(data: bytes) -> TextExtraction:
    text = ocr_image_bytes(data)
    out = TextExtraction(text=text, page_count=1, ocr_used=bool(text), engine="rapidocr")
    if not text:
        out.warnings.append("OCR produced no text from the image (unreadable or unsupported).")
    return out
