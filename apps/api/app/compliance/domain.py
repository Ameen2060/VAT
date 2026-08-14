"""Regime-agnostic compliance primitives.

These carry **no** tax-regime-specific fields — they are the shared vocabulary every
regime's rule engine speaks: a severity scale, a verdict, a finding, a verification
gap, a data-integrity check, and the generic shape of a review result.

Regime-specific schemas layer on top:
  * `vat.schemas` re-exports these and adds the `Invoice` model + `ReviewResult`.
  * a future `ct.schemas` will add `CorporateTaxReturn` + its own result type.

Keeping them here means a second regime reuses `Finding`/`ReviewResultBase`/severity
verbatim instead of duplicating (and drifting from) the VAT definitions.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from pydantic import BaseModel, Field


# ── Regime discriminator ─────────────────────────────────────────────────────
class Regime(str, Enum):
    """Which UAE tax regime a document/review belongs to."""

    VAT = "vat"
    CT = "ct"  # Corporate Tax (Federal Decree-Law No. 47 of 2022)


# ── Shared scales / verdicts ─────────────────────────────────────────────────
class Party(str, Enum):
    """Which side of a transaction a finding's obligation falls on. Invoice-centric;
    regimes without two parties (e.g. an entity-level CT return) simply leave
    `Finding.affects` unset."""

    SUPPLIER = "supplier"
    RECIPIENT = "recipient"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComplianceStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class Conclusion(str, Enum):
    """The three-way analyst conclusion shown to users. PASS = evidence supports the
    treatment; FAIL = a clear error was found; REVIEW = not enough information (or a
    cross-border assessment is needed) to conclude reliably."""

    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Findings, verification, validation ───────────────────────────────────────
class Finding(BaseModel):
    """A deterministic rule outcome. `rule_id`/`legal_ref` make every verdict
    auditable back to the specific rule and its legal basis."""

    rule_id: str
    severity: Severity
    title: str
    detail: str
    legal_ref: str | None = None
    affects: Party | None = None                # whose obligation this touches
    recommendation: str | None = None


class VerificationItem(BaseModel):
    """A field that could not be confidently extracted. Flagged for manual review —
    it does NOT by itself make a document non-compliant (an extraction gap is not a
    compliance failure)."""

    field: str
    label: str
    confidence: float = 0.0
    status: str = "not_detected"      # not_detected | low_confidence
    likely_present: bool = False      # raw text shows evidence the value exists
    reason: str = ""
    recommendation: str = ""


class ValidationCheck(BaseModel):
    """A data-integrity cross-check performed after extraction, before compliance."""

    name: str
    passed: bool
    detail: str


# ── Generic review result ────────────────────────────────────────────────────
class ReviewResultBase(BaseModel):
    """Regime-agnostic result of a review. Regimes subclass this to add their own
    typed context (VAT adds invoice/transaction type + recomputed VAT; CT will add
    tax-period / entity context)."""

    compliance_status: ComplianceStatus
    risk_level: RiskLevel
    findings: list[Finding] = Field(default_factory=list)
    verification_items: list[VerificationItem] = Field(default_factory=list)
    validations: list[ValidationCheck] = Field(default_factory=list)
    requires_verification: bool = False
    summary: str = ""

    @property
    def failed(self) -> bool:
        return self.compliance_status == ComplianceStatus.FAIL


# ── Shared verdict derivation ────────────────────────────────────────────────
def status_and_risk(findings: Iterable[Finding]) -> tuple[ComplianceStatus, RiskLevel]:
    """Derive an overall verdict from findings' severities. Regime-agnostic: the
    highest severity present sets the status/risk. Any HIGH → FAIL; MEDIUM/LOW →
    WARNING; nothing (or INFO only) → PASS."""
    severities = {f.severity for f in findings}
    if Severity.HIGH in severities:
        return ComplianceStatus.FAIL, RiskLevel.HIGH
    if Severity.MEDIUM in severities:
        return ComplianceStatus.WARNING, RiskLevel.MEDIUM
    if Severity.LOW in severities:
        return ComplianceStatus.WARNING, RiskLevel.LOW
    return ComplianceStatus.PASS, RiskLevel.LOW
