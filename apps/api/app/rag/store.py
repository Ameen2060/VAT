"""Ingestion and retrieval over the knowledge base."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KnowledgeChunk, KnowledgeDocument
from .embeddings import cosine, get_embedder


@dataclass
class RetrievedChunk:
    text: str
    source_ref: str | None
    title: str
    score: float


def chunk_text(text: str, target_chars: int = 900, overlap: int = 150) -> list[str]:
    """Split on blank lines, then pack paragraphs into ~target_chars windows."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= target_chars:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) > target_chars:
                # hard-split an over-long paragraph
                for i in range(0, len(p), target_chars - overlap):
                    chunks.append(p[i : i + target_chars])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks


def ingest_document(
    db: Session,
    *,
    title: str,
    text: str,
    source_ref: str | None = None,
    filename: str | None = None,
    category: str = "reference",
) -> KnowledgeDocument:
    embedder = get_embedder()
    doc = KnowledgeDocument(
        title=title, source_ref=source_ref, filename=filename, category=category
    )
    db.add(doc)
    db.flush()

    pieces = chunk_text(text)
    for i, piece in enumerate(pieces):
        db.add(
            KnowledgeChunk(
                document_id=doc.id,
                ordinal=i,
                text=piece,
                source_ref=source_ref,
                embedding=embedder.embed(piece),
                embedder=embedder.name,
            )
        )
    doc.chunk_count = len(pieces)
    db.commit()
    db.refresh(doc)
    return doc


def retrieve(db: Session, query: str, k: int = 5) -> list[RetrievedChunk]:
    embedder = get_embedder()
    qvec = embedder.embed(query)

    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument.title).join(
            KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id
        )
    ).all()

    scored: list[RetrievedChunk] = []
    for chunk, title in rows:
        emb = chunk.embedding or []
        # Only compare vectors from the same embedder / dimensionality.
        if chunk.embedder != embedder.name or len(emb) != len(qvec):
            continue
        scored.append(
            RetrievedChunk(
                text=chunk.text,
                source_ref=chunk.source_ref,
                title=title,
                score=cosine(qvec, emb),
            )
        )
    scored.sort(key=lambda r: r.score, reverse=True)
    return [r for r in scored[:k] if r.score > 0]


def build_context(chunks: list[RetrievedChunk]) -> tuple[str, list[str]]:
    """Format retrieved chunks into a context string + a de-duplicated citation list."""
    blocks, citations = [], []
    for i, c in enumerate(chunks, start=1):
        ref = c.source_ref or c.title
        blocks.append(f"[{i}] Source: {ref}\n{c.text}")
        if ref and ref not in citations:
            citations.append(ref)
    return "\n\n".join(blocks), citations
