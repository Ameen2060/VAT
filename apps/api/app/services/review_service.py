"""Review orchestration: store → extract → rule engine → AI advisory → persist."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ai.factory import get_ai_provider
from ..models import Document, Review
from ..vat.rules import review_invoice
from ..vat.schemas import Invoice
from ..vat.tax_codes import load_master
from . import report as report_svc
from .extraction import extract_invoices
from .storage import get_storage


def process_upload(
    db: Session,
    *,
    filename: str,
    data: bytes,
    mime: str | None = None,
    category: str = "invoice",
) -> list[Review]:
    """Run the full pipeline for one uploaded file and persist the result(s)."""
    storage = get_storage()
    provider = get_ai_provider()

    key = storage.save(filename, data)
    document = Document(
        filename=filename,
        mime=mime,
        size_bytes=len(data),
        storage_key=key,
        category=category,
    )
    db.add(document)
    db.flush()  # assign document.id

    tax_master = load_master(db)
    reviews: list[Review] = []
    for doc in extract_invoices(filename, data, mime):
        invoice = doc.invoice
        result = review_invoice(invoice, doc.raw_text or "", tax_master=tax_master)
        advisory = provider.advise(invoice, result, doc.raw_text)

        review = Review(
            document_id=document.id,
            invoice_json=invoice.model_dump(mode="json"),
            result_json=result.model_dump(mode="json"),
            advisory_json=advisory.model_dump(mode="json"),
            compliance_status=result.compliance_status.value,
            risk_level=result.risk_level.value,
            status="draft",
            doc_type=invoice.invoice_type.value,
            raw_text=doc.raw_text,
            ocr_used=doc.ocr_used,
            ocr_engine=doc.ocr_engine,
            extraction_warnings=doc.warnings,
        )
        db.add(review)
        reviews.append(review)

    db.commit()
    for r in reviews:
        db.refresh(r)
    return reviews


def reanalyze_advisory(db: Session, review: Review) -> Review:
    """Regenerate the AI advisory for an existing review using the current provider.

    Lets a user activate real AI (after adding a key) on already-uploaded documents
    without re-uploading."""
    provider = get_ai_provider()
    invoice = Invoice.model_validate(review.invoice_json or {})
    result = review_invoice(invoice, review.raw_text or "", tax_master=load_master(db))
    advisory = provider.advise(invoice, result, review.raw_text)
    review.advisory_json = advisory.model_dump(mode="json")
    db.commit()
    db.refresh(review)
    return review


def _doc_block(review: Review) -> str:
    inv = review.invoice_json or {}
    sup = (inv.get("supplier") or {}).get("name")
    findings = (review.result_json or {}).get("findings", [])
    finding_lines = "; ".join(f"{f.get('severity')}: {f.get('title')}" for f in findings) or "none"
    raw = (review.raw_text or "")[:1500]
    return (
        f"--- Document: {inv.get('invoice_number') or review.id} ({review.doc_type}) ---\n"
        f"Supplier: {sup}; Recipient: {(inv.get('recipient') or {}).get('name')}\n"
        f"Supplier TRN: {(inv.get('supplier') or {}).get('trn')}; "
        f"Recipient TRN: {(inv.get('recipient') or {}).get('trn')}\n"
        f"Currency: {inv.get('currency')}; Net: {inv.get('total_net')}; "
        f"VAT: {inv.get('total_vat')}; Gross: {inv.get('total_gross')}\n"
        f"Verdict: {review.compliance_status}/{review.risk_level}; Findings: {finding_lines}\n"
        f"Raw text (excerpt): {raw}\n"
    )


def combined_analysis(db: Session, reviews: list[Review]) -> dict:
    """Cross-document AI analysis over multiple reviews."""
    provider = get_ai_provider()
    block = "\n".join(_doc_block(r) for r in reviews)
    if hasattr(provider, "combined_analysis"):
        result = provider.combined_analysis(block)  # type: ignore[attr-defined]
    else:
        # Offline: deterministic cross-document summary.
        from ..ai.base import AdvisoryResult

        total_gross = sum(
            float((r.invoice_json or {}).get("total_gross") or 0) for r in reviews
        )
        fails = [r for r in reviews if r.compliance_status == "fail"]
        result = AdvisoryResult(
            narrative=(
                f"Portfolio of {len(reviews)} document(s). "
                f"{len(fails)} failed the rule engine; combined recorded gross ≈ {total_gross:,.2f}. "
                "Configure an AI provider for cross-document interpretation and anomaly detection."
            ),
            provider="stub",
            llm_used=False,
        )
    return result.model_dump(mode="json")


def build_report_payload(review: Review) -> dict:
    """Assemble the full data payload the report builder needs from a Review."""
    doc = review.document
    return {
        "invoice_json": review.invoice_json or {},
        "result_json": review.result_json or {},
        "advisory_json": review.advisory_json or {},
        "doc_type": review.doc_type,
        "meta": {
            "id": review.id,
            "filename": doc.filename if doc else None,
            "doc_type": review.doc_type,
            "status": review.status,
            "compliance_status": review.compliance_status,
            "risk_level": review.risk_level,
            "ocr_used": review.ocr_used,
            "ocr_engine": review.ocr_engine,
            "created_at": review.created_at.strftime("%Y-%m-%d %H:%M UTC") if review.created_at else None,
            "updated_at": review.updated_at.strftime("%Y-%m-%d %H:%M UTC") if review.updated_at else None,
            "report_generated_at": (
                review.report_generated_at.strftime("%Y-%m-%d %H:%M UTC")
                if review.report_generated_at
                else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            ),
        },
    }


def generate_report(db: Session, review: Review) -> Review:
    """Generate the combined PDF, store it, and link it to the review (regenerable)."""
    payload = build_report_payload(review)
    pdf = report_svc.build_report_pdf(payload)
    if pdf is None:
        raise RuntimeError("PDF generation is unavailable (install the 'report' extra: reportlab).")

    storage = get_storage()
    # Replace any previous report file for this review.
    if review.report_key:
        try:
            storage.delete(review.report_key)
        except Exception:  # noqa: BLE001
            pass
    review.report_key = storage.save(f"review-report-{review.id}.pdf", pdf)
    review.report_generated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)
    return review


def get_or_generate_report_bytes(db: Session, review: Review) -> bytes:
    """Return the stored report bytes, generating + storing it first if absent."""
    storage = get_storage()
    if review.report_key:
        try:
            return storage.read(review.report_key)
        except Exception:  # noqa: BLE001 — stored file missing; regenerate
            pass
    generate_report(db, review)
    return storage.read(review.report_key)


def rereview(db: Session, review: Review, invoice_patch: dict) -> Review:
    """Apply user edits to the extracted invoice, re-run the rule engine, and persist.

    Preserves the immutable original in extraction; only the working invoice + verdict
    are updated (version history is added in a later phase)."""
    merged = {**(review.invoice_json or {}), **invoice_patch}
    invoice = Invoice.model_validate(merged)
    result = review_invoice(invoice, review.raw_text or "", tax_master=load_master(db))

    review.invoice_json = invoice.model_dump(mode="json")
    review.result_json = result.model_dump(mode="json")
    review.compliance_status = result.compliance_status.value
    review.risk_level = result.risk_level.value
    review.doc_type = invoice.invoice_type.value
    db.commit()
    db.refresh(review)
    return review


def dashboard_summary(db: Session) -> dict:
    """Aggregate counts for the Home dashboard."""
    from sqlalchemy import func, select

    total = db.scalar(select(func.count()).select_from(Review)) or 0

    def _count(field, value) -> int:
        return db.scalar(select(func.count()).select_from(Review).where(field == value)) or 0

    return {
        "total_reviews": total,
        "high_risk": _count(Review.risk_level, "high"),
        "medium_risk": _count(Review.risk_level, "medium"),
        "low_risk": _count(Review.risk_level, "low"),
        "failed": _count(Review.compliance_status, "fail"),
        "warning": _count(Review.compliance_status, "warning"),
        "passed": _count(Review.compliance_status, "pass"),
        "pending_approval": _count(Review.status, "pending"),
        "approved": _count(Review.status, "approved"),
    }
