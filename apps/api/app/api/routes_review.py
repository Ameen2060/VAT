"""Invoice review API: upload, list, detail, approval workflow, report download."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..core.database import get_db
from ..models import Document, Review, User
from ..services import archive as archive_svc
from ..services import report as report_svc
from ..services.extraction import UnsupportedFileError
from ..services.field_extraction import missing_fields
from ..services.review_service import (
    dashboard_summary,
    generate_report,
    get_or_generate_report_bytes,
    process_upload,
    rereview,
)
from ..services.storage import get_storage
from ..vat.schemas import Invoice

router = APIRouter(prefix="/api", tags=["review"])

_VALID_STATUSES = {"draft", "pending", "approved", "rejected", "archived"}
_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


class ReviewSummary(BaseModel):
    review_id: str
    document_id: str
    filename: str
    compliance_status: str
    risk_level: str
    status: str
    read: bool
    summary: str


class StatusUpdate(BaseModel):
    status: str
    reviewer_notes: str | None = None


class ReadUpdate(BaseModel):
    read: bool = True


class InvoiceUpdate(BaseModel):
    """Partial invoice edits from the analysis UI (merged over the extracted invoice)."""

    invoice: dict


def _summary(r: Review, filename: str) -> ReviewSummary:
    return ReviewSummary(
        review_id=r.id,
        document_id=r.document_id,
        filename=filename,
        compliance_status=r.compliance_status,
        risk_level=r.risk_level,
        status=r.status,
        read=bool(r.is_read),
        summary=(r.result_json or {}).get("summary", ""),
    )


@router.post("/documents/upload", response_model=list[ReviewSummary])
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("invoice"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReviewSummary]:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        reviews = process_upload(
            db, filename=file.filename or "upload", data=data, mime=file.content_type, category=category
        )
    except UnsupportedFileError as e:
        raise HTTPException(status_code=415, detail=str(e)) from e
    if not reviews:
        raise HTTPException(status_code=422, detail="No invoice could be extracted from the file.")
    # Archive the original upload, linked to the (first) review it produced.
    archive_svc.archive_file(
        db, filename=file.filename or "upload", data=data, mime=file.content_type,
        source=archive_svc.SOURCE_DOCUMENT_ANALYSIS,
        review_id=reviews[0].id, document_id=reviews[0].document_id,
        uploaded_by=getattr(user, "email", None),
    )
    return [_summary(r, file.filename or "upload") for r in reviews]


@router.get("/reviews", response_model=list[ReviewSummary])
def list_reviews(
    risk: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[ReviewSummary]:
    stmt = select(Review, Document.filename).join(Document, Review.document_id == Document.id)
    if risk:
        stmt = stmt.where(Review.risk_level == risk)
    if status:
        stmt = stmt.where(Review.status == status)
    stmt = stmt.order_by(Review.created_at.desc())
    return [_summary(r, fn) for r, fn in db.execute(stmt).all()]


@router.get("/reviews/{review_id}")
def get_review(review_id: str, db: Session = Depends(get_db)) -> dict:
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "id": r.id,
        "document_id": r.document_id,
        "status": r.status,
        "read": bool(r.is_read),
        "reviewer_notes": r.reviewer_notes,
        "compliance_status": r.compliance_status,
        "risk_level": r.risk_level,
        "doc_type": r.doc_type,
        "invoice": r.invoice_json,
        "result": r.result_json,
        "advisory": r.advisory_json,
        "raw_text": r.raw_text,
        "ocr_used": r.ocr_used,
        "ocr_engine": r.ocr_engine,
        "extraction_warnings": r.extraction_warnings or [],
        "missing_fields": missing_fields(Invoice.model_validate(r.invoice_json or {})),
        "file_url": f"/api/documents/{r.document_id}/file",
        "has_report": bool(r.report_key),
        "report_url": f"/api/reviews/{r.id}/report/file",
        "report_generated_at": r.report_generated_at.isoformat() if r.report_generated_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.post("/reviews/{review_id}/report/generate")
def generate_review_report(review_id: str, db: Session = Depends(get_db)) -> dict:
    """Generate (or regenerate) the combined PDF report and store it on the review."""
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        generate_report(db, r)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {
        "id": r.id,
        "has_report": True,
        "report_url": f"/api/reviews/{r.id}/report/file",
        "report_generated_at": r.report_generated_at.isoformat() if r.report_generated_at else None,
    }


@router.get("/reviews/{review_id}/report/file")
def download_review_report(
    review_id: str, download: bool = Query(True), db: Session = Depends(get_db)
):
    """Download the stored combined PDF (generating + storing it if not present)."""
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        pdf = get_or_generate_report_bytes(db, r)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    disposition = "attachment" if download else "inline"
    inv_no = (r.invoice_json or {}).get("invoice_number") or r.id
    filename = f"VAT-Review-{inv_no}.pdf".replace("/", "-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.patch("/reviews/{review_id}/invoice")
def update_invoice(review_id: str, body: InvoiceUpdate, db: Session = Depends(get_db)) -> dict:
    """Save user-corrected extracted fields and re-run the compliance check."""
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        rereview(db, r, body.invoice)
    except Exception as e:  # noqa: BLE001 — surface validation issues to the UI
        raise HTTPException(status_code=422, detail=f"Invalid invoice data: {e}") from e
    return {"id": r.id, "compliance_status": r.compliance_status, "risk_level": r.risk_level}


@router.delete("/reviews/{review_id}")
def delete_review(review_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete a single review. Removes the parent document + stored file only if no
    other review references it (keeps other invoices from a multi-doc/ZIP upload)."""
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    document_id = r.document_id
    db.delete(r)
    db.flush()

    remaining = (
        db.scalar(
            select(func.count()).select_from(Review).where(Review.document_id == document_id)
        )
        or 0
    )
    if remaining == 0:
        doc = db.get(Document, document_id)
        if doc:
            try:
                get_storage().delete(doc.storage_key)
            except Exception:  # noqa: BLE001 — file cleanup is best-effort
                pass
            db.delete(doc)
    db.commit()
    return {"deleted": review_id}


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: str, db: Session = Depends(get_db)):
    """Stream the original uploaded document (for preview in the analysis UI)."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        data = get_storage().read(doc.storage_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Stored file unavailable") from e
    ext = "." + doc.filename.rsplit(".", 1)[-1].lower() if "." in doc.filename else ""
    media = doc.mime or _MIME_BY_EXT.get(ext, "application/octet-stream")
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.get("/documents/{document_id}/page/{page}")
def get_document_page(document_id: str, page: int, scale: float = 2.0, db: Session = Depends(get_db)):
    """Render one page of the document to PNG, so the UI can overlay source-evidence
    highlights on a raster image (works for both PDFs and image uploads)."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        data = get_storage().read(doc.storage_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Stored file unavailable") from e
    lower = doc.filename.lower()
    scale = max(1.0, min(float(scale), 4.0))
    if lower.endswith(".pdf"):
        try:
            import fitz
            d = fitz.open(stream=data, filetype="pdf")
            if page < 0 or page >= d.page_count:
                raise HTTPException(status_code=404, detail="Page out of range")
            pix = d[page].get_pixmap(matrix=fitz.Matrix(scale, scale))
            return Response(content=pix.tobytes("png"), media_type="image/png")
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Could not render PDF page") from e
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff", ".bmp")):
        ext = "." + lower.rsplit(".", 1)[-1]
        return Response(content=data, media_type=_MIME_BY_EXT.get(ext, "image/png"))
    raise HTTPException(status_code=400, detail="No page image available for this file type")


@router.patch("/reviews/{review_id}/status")
def update_status(review_id: str, body: StatusUpdate, db: Session = Depends(get_db)) -> dict:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {_VALID_STATUSES}")
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    r.status = body.status
    if body.reviewer_notes is not None:
        r.reviewer_notes = body.reviewer_notes
    db.commit()
    return {"id": r.id, "status": r.status}


@router.patch("/reviews/{review_id}/read")
def update_read(review_id: str, body: ReadUpdate, db: Session = Depends(get_db)) -> dict:
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    r.is_read = body.read
    db.commit()
    return {"id": r.id, "read": r.is_read}


@router.get("/reviews/{review_id}/report")
def download_report(
    review_id: str, format: str = Query("pdf", pattern="^(pdf|html)$"), db: Session = Depends(get_db)
):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    payload = {
        "invoice_json": r.invoice_json,
        "result_json": r.result_json,
        "advisory_json": r.advisory_json,
    }
    if format == "html":
        return HTMLResponse(report_svc.build_html(payload))
    pdf = report_svc.build_pdf(payload)
    if pdf is None:
        # reportlab not installed — fall back to HTML so the endpoint still works.
        return HTMLResponse(
            report_svc.build_html(payload),
            headers={"X-Report-Note": "PDF unavailable (install the 'report' extra); served HTML."},
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="vat-report-{review_id}.pdf"'},
    )


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    return dashboard_summary(db)
