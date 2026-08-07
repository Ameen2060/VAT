"""Knowledge base API: seed, ingest official documents, search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import KnowledgeChunk, KnowledgeDocument
from ..rag.seed import SEED_ENTRIES
from ..rag.store import ingest_document, retrieve
from ..services.extraction import document_text

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeDoc(BaseModel):
    id: str
    title: str
    source_ref: str | None
    category: str
    chunk_count: int


class SearchHit(BaseModel):
    text: str
    source_ref: str | None
    title: str
    score: float


@router.post("/seed")
def seed(db: Session = Depends(get_db)) -> dict:
    """Load the bundled seed corpus. Idempotent: skips if already present."""
    existing = {
        t for (t,) in db.execute(select(KnowledgeDocument.title)).all()
    }
    added = 0
    for entry in SEED_ENTRIES:
        if entry["title"] in existing:
            continue
        ingest_document(
            db,
            title=entry["title"],
            text=entry["text"],
            source_ref=entry["source_ref"],
            category="seed",
        )
        added += 1
    total = db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
    return {"added": added, "total_documents": total}


@router.post("/ingest", response_model=KnowledgeDoc)
async def ingest(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    source_ref: str | None = Form(None),
    category: str = Form("reference"),
    db: Session = Depends(get_db),
) -> KnowledgeDoc:
    data = await file.read()
    text = document_text(file.filename or "document", data)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="No extractable text (scanned PDFs need OCR — ingest a text-based source).",
        )
    doc = ingest_document(
        db,
        title=title or (file.filename or "Untitled"),
        text=text,
        source_ref=source_ref,
        filename=file.filename,
        category=category,
    )
    return KnowledgeDoc(
        id=doc.id,
        title=doc.title,
        source_ref=doc.source_ref,
        category=doc.category,
        chunk_count=doc.chunk_count,
    )


@router.get("/documents", response_model=list[KnowledgeDoc])
def list_documents(db: Session = Depends(get_db)) -> list[KnowledgeDoc]:
    docs = db.execute(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())).scalars()
    return [
        KnowledgeDoc(
            id=d.id, title=d.title, source_ref=d.source_ref, category=d.category, chunk_count=d.chunk_count
        )
        for d in docs
    ]


@router.get("/search", response_model=list[SearchHit])
def search(q: str = Query(..., min_length=2), k: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    hits = retrieve(db, q, k=k)
    return [SearchHit(text=h.text, source_ref=h.source_ref, title=h.title, score=round(h.score, 4)) for h in hits]
