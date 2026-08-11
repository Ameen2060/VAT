"""Archiving: every file attached to the system is stored here, durably.

Each archived file gets its own stored copy (independent storage key), so the
original is preserved unaltered and stays downloadable even if the related review
or VAT return is later deleted.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import ArchiveFile
from .storage import get_storage

# Canonical source labels.
SOURCE_DOCUMENT_ANALYSIS = "document_analysis"
SOURCE_INVOICE_REVIEW = "invoice_review"
SOURCE_VAT_RETURN = "vat_return"
SOURCE_ASSISTANT = "assistant"


def archive_file(
    db: Session,
    *,
    filename: str,
    data: bytes,
    mime: str | None,
    source: str,
    review_id: str | None = None,
    vat201_return_id: str | None = None,
    document_id: str | None = None,
    uploaded_by: str | None = None,
) -> ArchiveFile | None:
    """Store a durable copy of an uploaded file and index it in the archive.

    Best-effort: archiving must never break the primary upload flow, so any storage
    error is swallowed and None is returned.
    """
    try:
        key = get_storage().save(filename or "upload", data)
        entry = ArchiveFile(
            filename=filename or "upload",
            mime=mime,
            size_bytes=len(data),
            storage_key=key,
            source=source,
            review_id=review_id,
            vat201_return_id=vat201_return_id,
            document_id=document_id,
            uploaded_by=uploaded_by,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception:  # noqa: BLE001 — never fail the upload because archiving failed
        db.rollback()
        return None
