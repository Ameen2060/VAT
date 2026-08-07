"""Tests for the deterministic UAE VAT rule engine."""

from __future__ import annotations

from decimal import Decimal

from app.vat.rules import _valid_trn, review_invoice
from app.vat.schemas import (
    ComplianceStatus,
    Invoice,
    InvoiceType,
    LineItem,
    PartyDetails,
    RiskLevel,
    Severity,
    TransactionType,
    VatTreatment,
)

VALID_TRN = "100123456700003"  # 15 digits


def _finding_ids(result) -> set[str]:
    return {f.rule_id for f in result.findings}


# ── TRN validation ───────────────────────────────────────────────────────────
def test_trn_validation():
    assert _valid_trn(VALID_TRN)
    assert not _valid_trn("12345")            # too short
    assert not _valid_trn("10012345670000A")  # non-digit
    assert not _valid_trn(None)
    assert not _valid_trn("")


# ── A fully compliant standard-rated invoice passes ──────────────────────────
def _compliant_invoice() -> Invoice:
    return Invoice(
        invoice_type=InvoiceType.TAX_INVOICE,
        invoice_number="INV-2026-0001",
        invoice_date="2026-08-01",
        supplier=PartyDetails(name="ACME Trading LLC", address="Dubai, UAE", trn=VALID_TRN),
        recipient=PartyDetails(name="Buyer FZE", address="Dubai, UAE", trn="100999888700003"),
        transaction_type=TransactionType.LOCAL,
        treatment=VatTreatment.STANDARD,
        currency="AED",
        total_net=Decimal("1000.00"),
        total_vat=Decimal("50.00"),
        total_gross=Decimal("1050.00"),
        has_tax_invoice_label=True,
        line_items=[
            LineItem(
                description="Consulting",
                quantity=Decimal("1"),
                unit_price=Decimal("1000.00"),
                net_amount=Decimal("1000.00"),
                vat_rate=Decimal("0.05"),
                vat_amount=Decimal("50.00"),
                treatment=VatTreatment.STANDARD,
                line_total=Decimal("1050.00"),
            )
        ],
    )


def test_compliant_invoice_passes():
    result = review_invoice(_compliant_invoice())
    assert result.compliance_status == ComplianceStatus.PASS
    assert result.risk_level == RiskLevel.LOW
    assert not [f for f in result.findings if f.severity in (Severity.HIGH, Severity.MEDIUM)]
    assert result.recomputed_vat == Decimal("50.00")


# ── Missing particulars → verification, NOT a compliance failure ─────────────
def _verify_fields(result) -> set[str]:
    return {v.field for v in result.verification_items}


def test_missing_supplier_trn_is_verification_not_fail():
    """An extraction gap (missing field) must NOT fail the invoice — it becomes a
    'requires verification' item instead."""
    inv = _compliant_invoice()
    inv.supplier.trn = None
    result = review_invoice(inv)
    assert result.compliance_status == ComplianceStatus.PASS  # no genuine violation
    assert result.requires_verification is True
    assert "supplier.trn" in _verify_fields(result)
    assert not result.findings  # no compliance finding for a missing field


def test_invalid_supplier_trn_format_fails():
    """A TRN that IS present but malformed is real, assessable non-compliance → FAIL."""
    inv = _compliant_invoice()
    inv.supplier.trn = "12345"
    result = review_invoice(inv)
    assert "SUP-TRN-002" in _finding_ids(result)
    assert result.compliance_status == ComplianceStatus.FAIL


def test_missing_number_and_date_become_verification():
    inv = _compliant_invoice()
    inv.invoice_number = None
    inv.invoice_date = ""
    result = review_invoice(inv)
    assert result.compliance_status == ComplianceStatus.PASS
    assert {"invoice_number", "invoice_date"} <= _verify_fields(result)


# ── VAT calculation errors ───────────────────────────────────────────────────
def test_line_vat_miscalculation_flagged():
    inv = _compliant_invoice()
    inv.line_items[0].vat_amount = Decimal("40.00")  # should be 50.00
    result = review_invoice(inv)
    assert "CALC-001" in _finding_ids(result)
    assert result.compliance_status == ComplianceStatus.FAIL


def test_totals_do_not_reconcile():
    inv = _compliant_invoice()
    inv.total_gross = Decimal("1100.00")  # net 1000 + vat 50 = 1050, not 1100
    result = review_invoice(inv)
    assert "CALC-002" in _finding_ids(result)


def test_rounding_tolerance_absorbs_one_fils():
    inv = _compliant_invoice()
    # 0.01 difference is within the 0.02 tolerance → no CALC finding
    inv.line_items[0].vat_amount = Decimal("50.01")
    inv.total_vat = Decimal("50.01")
    inv.total_gross = Decimal("1050.01")
    result = review_invoice(inv)
    assert "CALC-001" not in _finding_ids(result)


# ── Treatment vs rate consistency ────────────────────────────────────────────
def test_zero_rated_with_five_percent_flagged():
    inv = _compliant_invoice()
    inv.treatment = VatTreatment.ZERO_RATED
    inv.line_items[0].treatment = VatTreatment.ZERO_RATED
    inv.line_items[0].vat_rate = Decimal("0.05")  # inconsistent with zero-rated
    result = review_invoice(inv)
    assert "TRT-001" in _finding_ids(result)


# ── Simplified invoice conditions ────────────────────────────────────────────
def test_simplified_invoice_to_registered_recipient_over_threshold():
    inv = _compliant_invoice()
    inv.invoice_type = InvoiceType.SIMPLIFIED_TAX_INVOICE
    inv.total_gross = Decimal("15000.00")  # > 10,000 and recipient is registered
    result = review_invoice(inv)
    assert "SIMP-001" in _finding_ids(result)
    assert result.compliance_status == ComplianceStatus.FAIL


def test_simplified_invoice_allowed_small_value():
    inv = _compliant_invoice()
    inv.invoice_type = InvoiceType.SIMPLIFIED_TAX_INVOICE
    inv.recipient = PartyDetails()  # unregistered recipient
    inv.total_gross = Decimal("500.00")
    result = review_invoice(inv)
    assert "SIMP-001" not in _finding_ids(result)


# ── Reverse charge ───────────────────────────────────────────────────────────
def test_reverse_charge_with_vat_charged_flagged():
    inv = _compliant_invoice()
    inv.treatment = VatTreatment.REVERSE_CHARGE
    inv.transaction_type = TransactionType.IMPORT
    inv.total_vat = Decimal("50.00")  # supplier should not charge VAT under RCM
    result = review_invoice(inv)
    assert "RCM-002" in _finding_ids(result)


# ── Data validation cross-checks are surfaced ────────────────────────────────
def test_validations_present_on_result():
    result = review_invoice(_compliant_invoice())
    names = {c.name for c in result.validations}
    assert "Net + VAT = Gross" in names
    assert all(c.passed for c in result.validations)  # a clean invoice passes all checks


def test_calculation_error_fails_but_missing_fields_do_not():
    """Verdict reflects actual data: a real math error fails; missing fields don't."""
    inv = _compliant_invoice()
    inv.recipient = PartyDetails()  # missing recipient → verification only
    inv.total_gross = Decimal("9999.00")  # net 1000 + vat 50 ≠ 9999 → real error
    result = review_invoice(inv)
    assert "CALC-002" in _finding_ids(result)
    assert result.compliance_status == ComplianceStatus.FAIL
    assert "recipient.name" in {v.field for v in result.verification_items}
