"""Pydantic schemas for the UAE Corporate Tax (CT) domain.

Unlike VAT (a per-invoice, transactional model), CT is assessed **per entity, per tax
period** from financial-statement figures. `CorporateTaxReturn` is the normalised form
the CT rule engine consumes; the extraction layer (future work) turns audited financials
/ a CT computation into one of these objects.

The generic compliance primitives (Finding, verdict, etc.) are shared with VAT via
`app.compliance.domain`; `CTReviewResult` subclasses the regime-agnostic
`ReviewResultBase`.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from ..compliance.domain import ReviewResultBase


# ── Enumerations (CT-specific) ───────────────────────────────────────────────
class TaxpayerType(str, Enum):
    RESIDENT_JURIDICAL = "resident_juridical"      # UAE-incorporated company
    RESIDENT_NATURAL = "resident_natural"          # natural person in business
    NON_RESIDENT = "non_resident"                  # PE / UAE-sourced income
    UNKNOWN = "unknown"


class FreeZoneStatus(str, Enum):
    NOT_FREE_ZONE = "not_free_zone"
    FREE_ZONE = "free_zone"                         # in a Free Zone, standard CT
    QFZP = "qfzp"                                    # claims Qualifying Free Zone Person (0%)


# ── Core CT return model ─────────────────────────────────────────────────────
class CorporateTaxReturn(BaseModel):
    """Normalised, entity- and period-level CT return consumed by the rule engine.

    All monetary fields are AED. `None` means "not known / not extracted" (an extraction
    gap → verification item, never an automatic failure); an explicit value or `False` is
    treated as asserted data the rules may act on.
    """

    # ── Identity ──
    entity_name: str | None = None
    trn: str | None = None                          # CT Tax Registration Number
    taxpayer_type: TaxpayerType = TaxpayerType.RESIDENT_JURIDICAL

    # ── Registration ──
    is_ct_registered: bool | None = None
    licence_issue_month: int | None = None          # 1-12; drives FTA Decision 3/2024 deadline
    incorporation_date: str | None = None           # ISO date; for on/after 1 Mar 2024 rule
    registration_date: str | None = None            # ISO date the entity actually registered

    # ── Tax period ──
    tax_period_start: str | None = None             # ISO date
    tax_period_end: str | None = None               # ISO date
    filing_date: str | None = None                  # ISO date the return was/will be filed
    currency: str | None = "AED"

    # ── Classification flags ──
    free_zone_status: FreeZoneStatus = FreeZoneStatus.NOT_FREE_ZONE
    is_mne_group_member: bool | None = None         # global revenue ≥ EUR 750M (DMTT / SBR gate)
    elects_small_business_relief: bool = False

    # ── Financials (period) ──
    revenue: Decimal | None = None                  # total revenue for the period
    accounting_net_profit: Decimal | None = None    # per IFRS financial statements
    taxable_income: Decimal | None = None           # after CT adjustments, before loss relief
    corporate_tax_payable: Decimal | None = None    # tax stated on the return
    has_audited_financials: bool | None = None

    # ── Free Zone specifics ──
    qualifying_income: Decimal | None = None
    non_qualifying_revenue: Decimal | None = None

    # ── Adjustment inputs (for deduction-limitation rules & the computation bridge) ──
    non_deductible_expenses: Decimal | None = None  # Art. 33 add-backs (excl. entertainment)
    exempt_income: Decimal | None = None            # dividends + participation-exempt income
    net_interest_expense: Decimal | None = None
    tax_ebitda: Decimal | None = None               # tax-adjusted EBITDA
    entertainment_expense: Decimal | None = None
    entertainment_deduction_claimed: Decimal | None = None
    tax_loss_offset_claimed: Decimal | None = None
    foreign_tax_credit: Decimal | None = None

    # ── Participation exemption (Art. 23) inputs ──
    participation_exemption_claimed: bool = False
    participation_ownership_pct: Decimal | None = None      # e.g. 0.05 for 5%
    participation_acquisition_cost: Decimal | None = None   # AED
    participation_holding_months: int | None = None
    participation_subject_to_tax: bool | None = None        # subject to ≥9% tax

    # ── Transfer pricing / related parties ──
    has_related_party_transactions: bool | None = None
    related_party_transactions_total: Decimal | None = None     # aggregate RP transactions
    connected_person_payments_total: Decimal | None = None      # aggregate connected-person payments

    # ── Extraction metadata ──
    field_confidence: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None

    @property
    def is_qfzp(self) -> bool:
        return self.free_zone_status == FreeZoneStatus.QFZP


# ── Computation trace ────────────────────────────────────────────────────────
class ComputationLine(BaseModel):
    """One node in the profit→tax computation graph. Every line is traceable: what it is,
    how much, its kind, and (where relevant) the legal basis."""

    step: str                       # machine key, e.g. "accounting_profit"
    label: str                      # human label
    amount: Decimal
    kind: str                       # base | addback | deduction | subtotal | tax | credit | total
    legal_ref: str | None = None


class CTComputation(BaseModel):
    """Deterministic, traceable corporate-tax computation."""

    lines: list[ComputationLine] = Field(default_factory=list)
    taxable_income: Decimal = Decimal("0")
    tax_before_credits: Decimal = Decimal("0")
    foreign_tax_credit: Decimal = Decimal("0")
    ct_payable: Decimal = Decimal("0")
    effective_rate: Decimal | None = None
    small_business_relief_applied: bool = False
    qfzp: bool = False
    notes: list[str] = Field(default_factory=list)


# ── Result ───────────────────────────────────────────────────────────────────
class CTReviewResult(ReviewResultBase):
    """CT review result: the generic result plus CT-specific computed context."""

    taxpayer_type: TaxpayerType = TaxpayerType.UNKNOWN
    free_zone_status: FreeZoneStatus = FreeZoneStatus.NOT_FREE_ZONE
    small_business_relief_applied: bool = False
    computed_tax: Decimal | None = None             # engine's best-effort CT recomputation
    effective_rate: Decimal | None = None           # computed_tax / taxable_income
    computation: CTComputation | None = None        # full traceable computation graph
