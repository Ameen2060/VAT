"""SQLAlchemy ORM models.

Phase 1 persists uploaded documents and the reviews generated from them, with an
approval-workflow status field and full JSON snapshots of the extracted invoice,
the rule-engine result and the AI advisory (nothing is lost — Compliance History).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .compliance.domain import Regime
from .core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="reviewer")  # admin | reviewer | viewer
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(1024))
    category: Mapped[str] = mapped_column(String(64), default="invoice")
    # Which tax regime this document is reviewed under (vat | ct). Discriminator that
    # lets a single repository hold both VAT and Corporate Tax documents.
    regime: Mapped[str] = mapped_column(String(8), default=Regime.VAT.value, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    reviews: Mapped[list["Review"]] = relationship(back_populates="document")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    # Tax regime this review was produced under (vat | ct). Denormalised from the
    # parent document for fast per-regime dashboard/history filtering.
    regime: Mapped[str] = mapped_column(String(8), default=Regime.VAT.value, index=True)

    # Snapshots (immutable record of what was assessed)
    invoice_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    advisory_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Denormalised for fast dashboard queries
    compliance_status: Mapped[str] = mapped_column(String(16), default="warning")
    risk_level: Mapped[str] = mapped_column(String(16), default="low")

    # Document analysis / extraction metadata
    doc_type: Mapped[str] = mapped_column(String(32), default="unknown")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_used: Mapped[bool] = mapped_column(default=False)
    ocr_engine: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extraction_warnings: Mapped[list] = mapped_column(JSON, default=list)

    # Stored combined PDF report (object-storage key + timestamp)
    report_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    report_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Approval workflow: draft | pending | approved | rejected | archived
    status: Mapped[str] = mapped_column(String(16), default="draft")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    document: Mapped[Document] = relationship(back_populates="reviews")


class CtReturnRecord(Base):
    """A persisted Corporate Tax return + its review result (immutable JSON snapshots plus
    denormalised columns for dashboard/history queries). Mirrors the `Review` design."""

    __tablename__ = "ct_returns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    regime: Mapped[str] = mapped_column(String(8), default=Regime.CT.value, index=True)

    entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tax_period_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tax_period_end: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Immutable snapshots (the assessed return + engine result)
    return_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Denormalised for fast dashboard/history queries
    compliance_status: Mapped[str] = mapped_column(String(16), default="warning", index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="low", index=True)
    taxable_income: Mapped[str | None] = mapped_column(String(32), nullable=True)
    computed_tax: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Workflow state: draft | data_collection | validation | internal_review | tax_review |
    # management_approval | ready_for_filing | filed | under_fta_review | closed
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Vat201ReturnRecord(Base):
    __tablename__ = "vat201_returns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_trn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_type: Mapped[str] = mapped_column(String(16), default="quarter")
    period_label: Mapped[str] = mapped_column(String(32), default="")
    period_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(16), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    net_vat_due: Mapped[str] = mapped_column(String(32), default="0")
    is_refund: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    return_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # VAT311 refund application prepared from this return (null until prepared).
    refund311_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    transactions: Mapped[list["Vat201TxnRecord"]] = relationship(
        back_populates="vat_return", cascade="all, delete-orphan"
    )


class Vat201TxnRecord(Base):
    __tablename__ = "vat201_transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    return_id: Mapped[str] = mapped_column(ForeignKey("vat201_returns.id", ondelete="CASCADE"))
    row_index: Mapped[int] = mapped_column(Integer, default=0)
    date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    party: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    emirate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    treatment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    taxable_amount: Mapped[str] = mapped_column(String(32), default="0")
    vat_amount: Mapped[str] = mapped_column(String(32), default="0")
    boxes: Mapped[list] = mapped_column(JSON, default=list)

    vat_return: Mapped[Vat201ReturnRecord] = relationship(back_populates="transactions")


class KnowledgeDocument(Base):
    """A source document in the FTA knowledge base (guide, law extract, note)."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512))
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)  # citation label
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="reference")
    version: Mapped[int] = mapped_column(Integer, default=1)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    embedding: Mapped[list] = mapped_column(JSON, default=list)  # list[float]
    embedder: Mapped[str] = mapped_column(String(32), default="hashing")

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
