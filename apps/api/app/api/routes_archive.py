"""Archive API: browse, search, open and download every file attached to the system."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import require_admin
from ..core.database import get_db
from ..models import ArchiveFile, Review, User, Vat201ReturnRecord
from ..services.storage import get_storage

router = APIRouter(prefix="/api/archive", tags=["archive"])

# Soft-deleted files are recoverable for this long, then auto-purged.
RETENTION_DAYS = 30

_MIME_BY_EXT = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
    ".tiff": "image/tiff", ".bmp": "image/bmp", ".csv": "text/csv",
    ".txt": "text/plain", ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_SOURCE_LABELS = {
    "document_analysis": "Document Analysis",
    "invoice_review": "Invoice Review",
    "vat_return": "VAT Return",
    "assistant": "VAT Assistant",
}


class RelatedInfo(BaseModel):
    kind: str | None = None          # "review" | "vat_return" | None
    id: str | None = None
    label: str | None = None
    analysis_href: str | None = None  # frontend route to the analysis/details
    report_url: str | None = None     # API url to download the related report/analysis


class ArchiveEntry(BaseModel):
    id: str
    filename: str
    mime: str | None
    size_bytes: int
    source: str
    source_label: str
    uploaded_by: str | None
    created_at: str | None
    file_url: str
    related: RelatedInfo
    deleted_at: str | None = None
    deleted_by: str | None = None
    purge_in_days: int | None = None  # days until auto-purge (soft-deleted only)


def _mime_for(entry: ArchiveFile) -> str:
    if entry.mime:
        return entry.mime
    name = entry.filename.lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    return _MIME_BY_EXT.get(ext, "application/octet-stream")


def _related(entry: ArchiveFile, db: Session) -> RelatedInfo:
    if entry.review_id:
        r = db.get(Review, entry.review_id)
        if r:
            inv_no = (r.invoice_json or {}).get("invoice_number")
            label = f"Review · {r.compliance_status}" + (f" · {inv_no}" if inv_no else "")
            return RelatedInfo(
                kind="review", id=r.id, label=label,
                analysis_href=f"/analyze?id={r.id}",
                report_url=f"/api/reviews/{r.id}/report/file?download=1",
            )
    if entry.vat201_return_id:
        rec = db.get(Vat201ReturnRecord, entry.vat201_return_id)
        if rec:
            return RelatedInfo(
                kind="vat_return", id=rec.id,
                label=f"VAT201 · {rec.period_label or rec.id}",
                analysis_href="/vat-return",
                report_url=f"/api/vat201/returns/{rec.id}/export?format=pdf",
            )
    return RelatedInfo()


def _purge_in_days(e: ArchiveFile) -> int | None:
    if not e.deleted_at:
        return None
    deleted = e.deleted_at
    if deleted.tzinfo is None:
        deleted = deleted.replace(tzinfo=timezone.utc)
    remaining = (deleted + timedelta(days=RETENTION_DAYS)) - datetime.now(timezone.utc)
    return max(0, remaining.days)


def _entry(e: ArchiveFile, db: Session) -> ArchiveEntry:
    return ArchiveEntry(
        id=e.id, filename=e.filename, mime=_mime_for(e), size_bytes=e.size_bytes,
        source=e.source, source_label=_SOURCE_LABELS.get(e.source, e.source),
        uploaded_by=e.uploaded_by,
        created_at=e.created_at.isoformat() if e.created_at else None,
        file_url=f"/api/archive/{e.id}/file",
        related=_related(e, db),
        deleted_at=e.deleted_at.isoformat() if e.deleted_at else None,
        deleted_by=e.deleted_by,
        purge_in_days=_purge_in_days(e),
    )


def _purge_expired(db: Session) -> None:
    """Hard-delete soft-deleted files past the retention window (lazy cleanup)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    expired = list(
        db.execute(
            select(ArchiveFile).where(
                ArchiveFile.deleted_at.is_not(None), ArchiveFile.deleted_at < cutoff
            )
        ).scalars()
    )
    for e in expired:
        try:
            get_storage().delete(e.storage_key)
        except Exception:  # noqa: BLE001 — best-effort file cleanup
            pass
        db.delete(e)
    if expired:
        db.commit()


@router.get("", response_model=list[ArchiveEntry])
def list_archive(
    q: str | None = Query(None, description="filter by filename"),
    source: str | None = Query(None),
    deleted: bool = Query(False, description="show the Recently Deleted (soft-deleted) items"),
    db: Session = Depends(get_db),
) -> list[ArchiveEntry]:
    _purge_expired(db)
    stmt = select(ArchiveFile)
    if deleted:
        stmt = stmt.where(ArchiveFile.deleted_at.is_not(None)).order_by(ArchiveFile.deleted_at.desc())
    else:
        stmt = stmt.where(ArchiveFile.deleted_at.is_(None)).order_by(ArchiveFile.created_at.desc())
    if source:
        stmt = stmt.where(ArchiveFile.source == source)
    rows = list(db.execute(stmt).scalars())
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r.filename or "").lower()]
    return [_entry(r, db) for r in rows]


@router.get("/{archive_id}", response_model=ArchiveEntry)
def get_archive_entry(archive_id: str, db: Session = Depends(get_db)) -> ArchiveEntry:
    e = db.get(ArchiveFile, archive_id)
    if not e:
        raise HTTPException(status_code=404, detail="Archived file not found")
    return _entry(e, db)


@router.get("/{archive_id}/file")
def get_archive_file(
    archive_id: str, download: bool = Query(False), db: Session = Depends(get_db)
):
    """Stream the original archived file — inline (view) or as an attachment (download)."""
    e = db.get(ArchiveFile, archive_id)
    if not e:
        raise HTTPException(status_code=404, detail="Archived file not found")
    try:
        data = get_storage().read(e.storage_key)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Stored file unavailable") from ex
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type=_mime_for(e),
        headers={"Content-Disposition": f'{disposition}; filename="{e.filename}"'},
    )


@router.delete("/{archive_id}")
def delete_archive_file(
    archive_id: str,
    permanent: bool = Query(False, description="hard-delete now instead of soft-delete"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Remove an archived file (admin only).

    By default this is a **soft delete**: the file moves to Recently Deleted and stays
    recoverable (30 days) before auto-purge. Pass ``permanent=true`` to delete it (and
    its stored copy) immediately.
    """
    e = db.get(ArchiveFile, archive_id)
    if not e:
        raise HTTPException(status_code=404, detail="Archived file not found")
    if permanent:
        try:
            get_storage().delete(e.storage_key)
        except Exception:  # noqa: BLE001 — file cleanup is best-effort
            pass
        db.delete(e)
        db.commit()
        return {"deleted": archive_id, "permanent": True}
    e.deleted_at = datetime.now(timezone.utc)
    e.deleted_by = getattr(admin, "email", None)
    db.commit()
    return {"deleted": archive_id, "permanent": False, "recoverable_days": RETENTION_DAYS}


@router.post("/{archive_id}/restore", response_model=ArchiveEntry)
def restore_archive_file(
    archive_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ArchiveEntry:
    """Restore a soft-deleted archived file back to the archive (admin only)."""
    e = db.get(ArchiveFile, archive_id)
    if not e:
        raise HTTPException(status_code=404, detail="Archived file not found")
    e.deleted_at = None
    e.deleted_by = None
    db.commit()
    db.refresh(e)
    return _entry(e, db)


class BulkRequest(BaseModel):
    ids: list[str]
    action: str  # "delete" (soft) | "restore" | "permanent"


@router.post("/bulk")
def bulk_action(
    body: BulkRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Apply an action to several archived files at once (admin only)."""
    if body.action not in ("delete", "restore", "permanent"):
        raise HTTPException(status_code=400, detail="action must be delete | restore | permanent")
    processed = 0
    for aid in body.ids:
        e = db.get(ArchiveFile, aid)
        if not e:
            continue
        if body.action == "restore":
            e.deleted_at = None
            e.deleted_by = None
        elif body.action == "permanent":
            try:
                get_storage().delete(e.storage_key)
            except Exception:  # noqa: BLE001
                pass
            db.delete(e)
        else:  # soft delete
            e.deleted_at = datetime.now(timezone.utc)
            e.deleted_by = getattr(admin, "email", None)
        processed += 1
    db.commit()
    return {"processed": processed, "action": body.action}
