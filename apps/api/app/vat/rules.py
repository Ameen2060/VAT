"""Deterministic UAE VAT rule engine.

Each rule is a small pure function that inspects a normalised :class:`Invoice` and
yields zero or more :class:`Finding` objects. The engine runs every rule, then
derives an overall compliance status and risk level from the findings' severities.

Why deterministic (not AI): an auditor-facing verdict must be reproducible and
traceable to a specific article of law. The language model's job is extraction and
explanation, not adjudication.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from decimal import Decimal, ROUND_HALF_UP

from . import constants as C
from .schemas import (
    ComplianceStatus,
    Finding,
    Invoice,
    InvoiceType,
    Party,
    ReviewResult,
    RiskLevel,
    Severity,
    TransactionType,
    VatTreatment,
)

Rule = "callable that takes an Invoice and yields Findings"


# ── Helpers ──────────────────────────────────────────────────────────────────
def _is_blank(value: str | None) -> bool:
    return value is None or str(value).strip() == ""


def _valid_trn(trn: str | None) -> bool:
    if _is_blank(trn):
        return False
    digits = "".join(ch for ch in str(trn) if ch.isdigit())
    return len(digits) == C.TRN_LENGTH and digits == str(trn).strip()


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _requires_full_invoice(inv: Invoice) -> bool:
    """A full tax invoice (not simplified) is required unless the Art. 59(5)
    conditions are met: recipient unregistered OR consideration <= AED 10,000."""
    recipient_registered = _valid_trn(inv.recipient.trn)
    total = inv.total_gross or Decimal(0)
    simplified_allowed = (not recipient_registered) or total <= Decimal(str(C.SIMPLIFIED_INVOICE_MAX))
    return not simplified_allowed


# ── Rules: mandatory-particular FORMAT checks (present-but-wrong data only) ──
# IMPORTANT: a *missing* mandatory particular is NOT judged here. Missing/uncertain
# fields are handled by the validation layer as "requires verification" items, so an
# OCR/extraction gap can never make an invoice FAIL. These rules only fire on data
# that IS present on the document and is demonstrably non-compliant.
def rule_supplier_trn_format(inv: Invoice) -> Iterator[Finding]:
    if not _is_blank(inv.supplier.trn) and not _valid_trn(inv.supplier.trn):
        yield Finding(
            rule_id="SUP-TRN-002",
            severity=Severity.HIGH,
            title="Invalid supplier TRN format",
            detail=f"Supplier TRN '{inv.supplier.trn}' is not a valid 15-digit UAE TRN.",
            legal_ref=C.LEGAL_REFS["full_invoice_particulars"],
            affects=Party.SUPPLIER,
            recommendation="Verify the TRN on the FTA portal; it must be exactly 15 digits.",
        )


def rule_recipient_trn_format(inv: Invoice) -> Iterator[Finding]:
    if not _is_blank(inv.recipient.trn) and not _valid_trn(inv.recipient.trn):
        yield Finding(
            rule_id="REC-TRN-002",
            severity=Severity.MEDIUM,
            title="Invalid recipient TRN format",
            detail=f"Recipient TRN '{inv.recipient.trn}' is not a valid 15-digit UAE TRN.",
            legal_ref=C.LEGAL_REFS["full_invoice_particulars"],
            affects=Party.RECIPIENT,
            recommendation="Confirm the recipient TRN (15 digits) and validate on the FTA portal.",
        )


def rule_simplified_invoice_conditions(inv: Invoice) -> Iterator[Finding]:
    """A simplified tax invoice is only permitted where the recipient is not
    registered OR the consideration does not exceed AED 10,000 (Art. 59(5) ER)."""
    if inv.invoice_type != InvoiceType.SIMPLIFIED_TAX_INVOICE:
        return
    recipient_registered = _valid_trn(inv.recipient.trn)
    total = inv.total_gross or Decimal(0)
    if recipient_registered and total > Decimal(str(C.SIMPLIFIED_INVOICE_MAX)):
        yield Finding(
            rule_id="SIMP-001",
            severity=Severity.HIGH,
            title="Simplified invoice not permitted",
            detail=(
                "A simplified tax invoice was issued to a VAT-registered recipient for "
                f"consideration of AED {total} (> AED {C.SIMPLIFIED_INVOICE_MAX}). A full "
                "tax invoice is required."
            ),
            legal_ref=C.LEGAL_REFS["simplified_invoice_conditions"],
            affects=Party.SUPPLIER,
            recommendation="Re-issue as a full tax invoice with all Art. 59(1) particulars.",
        )


# ── Rules: reverse charge ────────────────────────────────────────────────────
def rule_reverse_charge(inv: Invoice) -> Iterator[Finding]:
    is_rcm = inv.treatment == VatTreatment.REVERSE_CHARGE or inv.transaction_type in (
        TransactionType.IMPORT,
    )
    if not is_rcm:
        return
    # Under RCM the supplier does not charge UAE VAT; the recipient self-accounts.
    if inv.total_vat and inv.total_vat > 0 and inv.treatment == VatTreatment.REVERSE_CHARGE:
        yield Finding(
            rule_id="RCM-002",
            severity=Severity.HIGH,
            title="VAT charged on a reverse-charge supply",
            detail=(
                "The supply is subject to the reverse charge mechanism, yet output VAT "
                "has been charged on the invoice. The recipient must self-account instead."
            ),
            legal_ref=C.LEGAL_REFS["reverse_charge"],
            affects=Party.RECIPIENT,
            recommendation=(
                "Supplier should not charge UAE VAT. Recipient accounts for output VAT and "
                "recovers input VAT (if recoverable) in the same return."
            ),
        )
    if inv.has_reverse_charge_statement is False:
        yield Finding(
            rule_id="RCM-001",
            severity=Severity.MEDIUM,
            title="Missing reverse-charge statement",
            detail="Where the reverse charge applies, the invoice should state so.",
            legal_ref=C.LEGAL_REFS["reverse_charge"],
            affects=Party.RECIPIENT,
            recommendation=(
                'Add a statement that the recipient must account for VAT under the reverse '
                "charge mechanism, and record the self-assessed VAT in Box 3 / Box 6/7 as "
                "applicable."
            ),
        )


# ── Rules: VAT treatment & calculation ───────────────────────────────────────
def rule_treatment_rate_consistency(inv: Invoice) -> Iterator[Finding]:
    if inv.treatment is None:
        return  # treatment not classified is an extraction gap → verification, not a finding
    for idx, li in enumerate(inv.line_items, start=1):
        if li.vat_rate is None:
            continue
        expected = {
            VatTreatment.STANDARD: Decimal(str(C.STANDARD_RATE)),
            VatTreatment.ZERO_RATED: Decimal("0"),
            VatTreatment.EXEMPT: Decimal("0"),
            VatTreatment.OUT_OF_SCOPE: Decimal("0"),
            VatTreatment.REVERSE_CHARGE: Decimal("0"),
        }.get(li.treatment or inv.treatment)
        if expected is not None and li.vat_rate != expected:
            yield Finding(
                rule_id="TRT-001",
                severity=Severity.HIGH,
                title=f"Line {idx}: VAT rate inconsistent with treatment",
                detail=(
                    f"Line {idx} is classified '{(li.treatment or inv.treatment).value}' but "
                    f"carries a rate of {li.vat_rate}. Expected {expected}."
                ),
                legal_ref=C.LEGAL_REFS["standard_rate"],
                affects=Party.SUPPLIER,
                recommendation="Align the applied rate with the correct VAT treatment.",
            )


def rule_vat_calculation(inv: Invoice) -> Iterator[Finding]:
    tol = Decimal(str(C.CALC_TOLERANCE_AED))

    # Per-line checks
    for idx, li in enumerate(inv.line_items, start=1):
        if li.net_amount is not None and li.vat_rate is not None and li.vat_amount is not None:
            expected = _round(li.net_amount * li.vat_rate)
            if abs(expected - li.vat_amount) > tol:
                yield Finding(
                    rule_id="CALC-001",
                    severity=Severity.HIGH,
                    title=f"Line {idx}: VAT amount does not match net × rate",
                    detail=(
                        f"Line {idx}: net {li.net_amount} × {li.vat_rate} = {expected}, but "
                        f"the invoice states {li.vat_amount}."
                    ),
                    legal_ref=C.LEGAL_REFS["rounding"],
                    affects=Party.SUPPLIER,
                    recommendation="Recompute VAT as net × rate, rounded to the nearest fils.",
                )

    # Header check: net + vat = gross
    if inv.total_net is not None and inv.total_vat is not None and inv.total_gross is not None:
        if abs((inv.total_net + inv.total_vat) - inv.total_gross) > tol:
            yield Finding(
                rule_id="CALC-002",
                severity=Severity.HIGH,
                title="Totals do not reconcile (net + VAT ≠ gross)",
                detail=(
                    f"Net {inv.total_net} + VAT {inv.total_vat} = "
                    f"{inv.total_net + inv.total_vat}, but the stated gross is {inv.total_gross}."
                ),
                legal_ref=C.LEGAL_REFS["full_invoice_particulars"],
                affects=Party.SUPPLIER,
                recommendation="Correct the arithmetic so net + VAT equals the gross total.",
            )

    # Header check: stated VAT vs recomputed from net at standard rate
    if (
        inv.treatment == VatTreatment.STANDARD
        and inv.total_net is not None
        and inv.total_vat is not None
    ):
        expected = _round(inv.total_net * Decimal(str(C.STANDARD_RATE)))
        if abs(expected - inv.total_vat) > tol:
            yield Finding(
                rule_id="CALC-003",
                severity=Severity.MEDIUM,
                title="Header VAT differs from 5% of net",
                detail=(
                    f"Expected 5% of net {inv.total_net} = {expected}; invoice states "
                    f"{inv.total_vat}. May be legitimate line-level rounding — verify."
                ),
                legal_ref=C.LEGAL_REFS["rounding"],
                affects=Party.SUPPLIER,
                recommendation="Confirm the VAT total aggregates correctly rounded line VAT.",
            )


def rule_exempt_recovery_note(inv: Invoice) -> Iterator[Finding]:
    if inv.treatment == VatTreatment.EXEMPT:
        yield Finding(
            rule_id="EXM-001",
            severity=Severity.INFO,
            title="Exempt supply — input VAT not recoverable",
            detail=(
                "Input VAT attributable to exempt supplies is not recoverable and may "
                "require apportionment where costs are used for mixed supplies."
            ),
            legal_ref=C.LEGAL_REFS["exempt"],
            affects=Party.RECIPIENT,
            recommendation="Apply the input tax apportionment method to residual input tax.",
        )


def rule_export_evidence_note(inv: Invoice) -> Iterator[Finding]:
    if inv.transaction_type == TransactionType.EXPORT or inv.treatment == VatTreatment.ZERO_RATED:
        yield Finding(
            rule_id="EXP-001",
            severity=Severity.LOW,
            title="Zero-rating requires supporting evidence",
            detail=(
                "Zero-rating an export must be supported by official and commercial "
                "evidence of export within the prescribed period, retained for audit."
            ),
            legal_ref=C.LEGAL_REFS["export_zero_rating"],
            affects=Party.SUPPLIER,
            recommendation=(
                "Retain customs exit certificate, shipping/airway bill and commercial "
                "evidence proving the goods left the UAE within 90 days."
            ),
        )


# ── Registry & engine ────────────────────────────────────────────────────────
# Only checks that assess data actually present on the document. Missing particulars
# are surfaced by the validation layer as verification items, never as failures.
ALL_RULES = [
    rule_supplier_trn_format,
    rule_recipient_trn_format,
    rule_simplified_invoice_conditions,
    rule_reverse_charge,
    rule_treatment_rate_consistency,
    rule_vat_calculation,
    rule_exempt_recovery_note,
    rule_export_evidence_note,
]


def _recompute_vat(inv: Invoice) -> Decimal | None:
    """Best-effort recomputation of total VAT for display/verification."""
    if inv.line_items:
        total = Decimal(0)
        seen = False
        for li in inv.line_items:
            if li.net_amount is not None and li.vat_rate is not None:
                total += _round(li.net_amount * li.vat_rate)
                seen = True
        if seen:
            return total
    if inv.treatment == VatTreatment.STANDARD and inv.total_net is not None:
        return _round(inv.total_net * Decimal(str(C.STANDARD_RATE)))
    return None


def _status_and_risk(findings: Iterable[Finding]) -> tuple[ComplianceStatus, RiskLevel]:
    severities = {f.severity for f in findings}
    if Severity.HIGH in severities:
        return ComplianceStatus.FAIL, RiskLevel.HIGH
    if Severity.MEDIUM in severities:
        return ComplianceStatus.WARNING, RiskLevel.MEDIUM
    if Severity.LOW in severities:
        return ComplianceStatus.WARNING, RiskLevel.LOW
    return ComplianceStatus.PASS, RiskLevel.LOW


def review_invoice(inv: Invoice, raw_text: str = "") -> ReviewResult:
    """Pipeline steps 4–7: validate the extracted data, flag anything needing manual
    verification, then run the deterministic compliance rules and derive the verdict.

    Crucially, the Pass/Fail verdict is based ONLY on genuine compliance findings
    (present data that violates a rule) — never on extraction gaps, which are surfaced
    separately as verification items.
    """
    from .validation import validate_invoice

    # Step 4: validation + verification flagging.
    verification_items, validations = validate_invoice(inv, raw_text)

    # Step 6: deterministic compliance rules (only assess data that is present).
    findings: list[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(inv))

    # Step 7: verdict — from compliance findings alone.
    status, risk = _status_and_risk(findings)
    highs = sum(1 for f in findings if f.severity == Severity.HIGH)
    meds = sum(1 for f in findings if f.severity == Severity.MEDIUM)
    lows = sum(1 for f in findings if f.severity == Severity.LOW)
    requires_verification = len(verification_items) > 0

    verify_note = (
        f" · {len(verification_items)} field(s) require verification" if requires_verification else ""
    )
    summary = (
        f"Compliance {status.value.upper()} · risk {risk.value.upper()} · "
        f"{highs} high, {meds} medium, {lows} low finding(s){verify_note}."
    )

    return ReviewResult(
        compliance_status=status,
        risk_level=risk,
        invoice_type=inv.invoice_type,
        transaction_type=inv.transaction_type,
        findings=findings,
        verification_items=verification_items,
        validations=validations,
        requires_verification=requires_verification,
        recomputed_vat=_recompute_vat(inv),
        summary=summary,
    )
