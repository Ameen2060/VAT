"""Pydantic schemas for the VAT domain.

These model a *structured* invoice — the normalised form the rule engine consumes.
The AI extraction layer (Phase 1) is responsible for turning a PDF/scan/spreadsheet
into one of these objects; the rule engine never sees raw files.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

# Regime-agnostic primitives live in app.compliance and are re-exported here so
# existing imports (`from app.vat.schemas import Finding`, ...) keep working unchanged.
from ..compliance.domain import (  # noqa: F401  (re-exported for backwards compat)
    ComplianceStatus,
    Finding,
    Party,
    ReviewResultBase,
    RiskLevel,
    Severity,
    ValidationCheck,
    VerificationItem,
)


# ── Enumerations (VAT-specific) ──────────────────────────────────────────────
class InvoiceType(str, Enum):
    TAX_INVOICE = "tax_invoice"
    SIMPLIFIED_TAX_INVOICE = "simplified_tax_invoice"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    RECEIPT = "receipt"
    INVOICE = "invoice"
    UNKNOWN = "unknown"


class VatTreatment(str, Enum):
    STANDARD = "standard"          # 5%
    ZERO_RATED = "zero_rated"      # 0%
    EXEMPT = "exempt"              # no VAT, no input recovery
    OUT_OF_SCOPE = "out_of_scope"  # outside UAE VAT scope
    REVERSE_CHARGE = "reverse_charge"


class TransactionType(str, Enum):
    LOCAL = "local"
    IMPORT = "import"
    EXPORT = "export"
    GCC = "gcc"
    DESIGNATED_ZONE = "designated_zone"
    UNKNOWN = "unknown"


# Party, Severity, ComplianceStatus and RiskLevel are regime-agnostic and now live in
# app.compliance.domain (imported/re-exported at the top of this module).


# ── Core invoice models ──────────────────────────────────────────────────────
class PartyDetails(BaseModel):
    name: str | None = None
    address: str | None = None
    trn: str | None = None
    phone: str | None = None
    email: str | None = None


class PaymentInfo(BaseModel):
    bank_name: str | None = None
    account_name: str | None = None
    account_number: str | None = None
    iban: str | None = None
    swift: str | None = None
    terms: str | None = None


class LineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    net_amount: Decimal | None = None          # amount before VAT
    vat_rate: Decimal | None = None            # e.g. 0.05
    vat_amount: Decimal | None = None
    treatment: VatTreatment | None = None
    line_total: Decimal | None = None          # net + vat


class Invoice(BaseModel):
    """Normalised invoice consumed by the rule engine."""

    # Identity
    invoice_type: InvoiceType = InvoiceType.UNKNOWN
    invoice_number: str | None = None
    invoice_date: str | None = None            # ISO date string; parsed leniently
    supply_date: str | None = None             # date of supply, if different
    due_date: str | None = None

    # Parties
    supplier: PartyDetails = Field(default_factory=PartyDetails)
    recipient: PartyDetails = Field(default_factory=PartyDetails)

    # Classification
    transaction_type: TransactionType = TransactionType.UNKNOWN
    treatment: VatTreatment | None = None       # header-level treatment, if uniform

    # Amounts (header totals)
    currency: str | None = "AED"
    exchange_rate: Decimal | None = None
    total_net: Decimal | None = None
    total_vat: Decimal | None = None
    total_gross: Decimal | None = None
    discount_amount: Decimal | None = None

    # Detail
    line_items: list[LineItem] = Field(default_factory=list)

    # Payment
    payment: PaymentInfo | None = None

    # Wording flags (presence of required statements on the document)
    has_tax_invoice_label: bool | None = None
    has_reverse_charge_statement: bool | None = None
    has_zero_rated_statement: bool | None = None

    # Per-field extraction confidence (0..1), keyed by field path e.g. "invoice_number".
    field_confidence: dict[str, float] = Field(default_factory=dict)

    # Level-4 source evidence: for each extracted field, where in the document text the
    # value was found — {field_path: {"snippet": str, "line_no": int, "start": int, "end": int}}.
    # Lets the UI trace every value back to its exact location in the original document.
    field_evidence: dict[str, dict] = Field(default_factory=dict)

    # Free-form notes captured during extraction
    notes: str | None = None


# ── Findings & result ────────────────────────────────────────────────────────
# Finding, VerificationItem and ValidationCheck are regime-agnostic and now live in
# app.compliance.domain (imported/re-exported at the top of this module).


class ReviewResult(ReviewResultBase):
    """VAT review result: the generic result (status, risk, findings, verification,
    validations, summary) plus VAT-specific classification and the engine's
    recomputed VAT total."""

    invoice_type: InvoiceType
    transaction_type: TransactionType
    recomputed_vat: Decimal | None = None
