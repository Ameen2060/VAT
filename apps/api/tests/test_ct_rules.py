"""Tests for the deterministic UAE Corporate Tax (CT) rule engine.

The rule set is PROVISIONAL (pending SME validation) but its *behaviour* is pinned here
so future edits are deliberate.
"""

from __future__ import annotations

from decimal import Decimal

from app.compliance.domain import ComplianceStatus, RiskLevel, Severity
from app.ct.computation import compute_ct
from app.ct.rules import (
    expected_standard_tax,
    registration_deadline,
    review_ct_return,
)
from app.ct.schemas import CorporateTaxReturn, FreeZoneStatus, TaxpayerType

VALID_TRN = "100123456700003"  # 15 digits


def _ids(result) -> set[str]:
    return {f.rule_id for f in result.findings}


# ── A clean, standard resident company passes ────────────────────────────────
def _clean_return() -> CorporateTaxReturn:
    # Taxable income 500,000 → CT = 9% × (500,000 − 375,000) = 11,250.
    return CorporateTaxReturn(
        entity_name="ACME Trading LLC",
        trn=VALID_TRN,
        taxpayer_type=TaxpayerType.RESIDENT_JURIDICAL,
        is_ct_registered=True,
        tax_period_start="2024-01-01",
        tax_period_end="2024-12-31",
        filing_date="2025-06-30",  # within 9 months
        revenue=Decimal("2000000"),
        accounting_net_profit=Decimal("500000"),
        taxable_income=Decimal("500000"),
        corporate_tax_payable=Decimal("11250"),
        has_audited_financials=True,
    )


def test_clean_return_passes():
    result = review_ct_return(_clean_return())
    assert result.compliance_status == ComplianceStatus.PASS
    assert result.risk_level == RiskLevel.LOW
    assert not result.failed
    assert result.computed_tax == Decimal("11250")
    # No HIGH/MEDIUM/LOW findings (INFO is allowed).
    assert all(f.severity == Severity.INFO for f in result.findings)


# ── Rate band maths ──────────────────────────────────────────────────────────
def test_expected_standard_tax_bands():
    assert expected_standard_tax(Decimal("375000")) == Decimal("0")
    assert expected_standard_tax(Decimal("300000")) == Decimal("0")
    assert expected_standard_tax(Decimal("475000")) == Decimal("9000.00")  # 9% of 100k


def test_wrong_tax_amount_flags_ct_rate_001():
    ret = _clean_return()
    ret.corporate_tax_payable = Decimal("45000")  # wrong (9% of full income, no threshold)
    result = review_ct_return(ret)
    assert "CT-RATE-001" in _ids(result)
    assert result.compliance_status == ComplianceStatus.FAIL


# ── Registration ─────────────────────────────────────────────────────────────
def test_unregistered_entity_fails():
    ret = _clean_return()
    ret.is_ct_registered = False
    result = review_ct_return(ret)
    assert "CT-REG-001" in _ids(result)
    assert result.failed


def test_registration_deadline_schedule_and_late_flag():
    # Licence issued in a March → deadline 30 Jun 2024 (FTA Decision 3/2024).
    ret = _clean_return()
    ret.licence_issue_month = 3
    ret.registration_date = "2024-09-01"  # after the deadline
    assert registration_deadline(ret).isoformat() == "2024-06-30"
    result = review_ct_return(ret)
    assert "CT-REG-002" in _ids(result)


# ── Filing deadline ──────────────────────────────────────────────────────────
def test_late_filing_flags_ct_file_001():
    ret = _clean_return()
    ret.filing_date = "2025-10-15"  # > 9 months after 2024-12-31
    result = review_ct_return(ret)
    assert "CT-FILE-001" in _ids(result)


# ── Small Business Relief ────────────────────────────────────────────────────
def test_sbr_available_is_info_only():
    ret = _clean_return()
    ret.revenue = Decimal("2500000")  # ≤ 3M, period ends 2024 → eligible
    result = review_ct_return(ret)
    assert "CT-SBR-001" in _ids(result)
    # Info-only relief availability must not, by itself, fail the return.
    assert result.compliance_status != ComplianceStatus.FAIL


def test_sbr_elected_but_mne_member_is_ineligible():
    ret = _clean_return()
    ret.revenue = Decimal("2500000")
    ret.elects_small_business_relief = True
    ret.is_mne_group_member = True
    result = review_ct_return(ret)
    assert "CT-SBR-002" in _ids(result)


def test_sbr_elected_over_threshold_is_high():
    ret = _clean_return()
    ret.elects_small_business_relief = True
    ret.revenue = Decimal("5000000")  # > 3M
    result = review_ct_return(ret)
    assert "CT-SBR-003" in _ids(result)
    assert result.failed


def test_valid_sbr_makes_tax_nil_and_applies():
    ret = _clean_return()
    ret.revenue = Decimal("2500000")
    ret.elects_small_business_relief = True
    ret.corporate_tax_payable = Decimal("0")
    result = review_ct_return(ret)
    assert result.small_business_relief_applied
    assert result.computed_tax == Decimal("0")
    assert "CT-RATE-001" not in _ids(result)


# ── Free Zone (QFZP) ─────────────────────────────────────────────────────────
def test_qfzp_de_minimis_breach_is_high():
    ret = _clean_return()
    ret.free_zone_status = FreeZoneStatus.QFZP
    ret.revenue = Decimal("10000000")
    ret.non_qualifying_revenue = Decimal("2000000")  # > lower(5M, 5% of 10M = 500k)
    result = review_ct_return(ret)
    assert "CT-FZ-001" in _ids(result)
    assert result.failed


def test_qfzp_missing_audited_fs_is_medium():
    ret = _clean_return()
    ret.free_zone_status = FreeZoneStatus.QFZP
    ret.has_audited_financials = False
    result = review_ct_return(ret)
    assert "CT-FZ-002" in _ids(result)


# ── Deduction limitations ────────────────────────────────────────────────────
def test_interest_limitation():
    ret = _clean_return()
    ret.tax_ebitda = Decimal("10000000")            # 30% = 3M, but de minimis 12M wins
    ret.net_interest_expense = Decimal("13000000")  # > 12M → excess disallowed
    result = review_ct_return(ret)
    assert "CT-INT-001" in _ids(result)


def test_entertainment_over_50_percent():
    ret = _clean_return()
    ret.entertainment_expense = Decimal("100000")
    ret.entertainment_deduction_claimed = Decimal("80000")  # > 50%
    result = review_ct_return(ret)
    assert "CT-ENT-001" in _ids(result)


def test_loss_offset_over_75_percent():
    ret = _clean_return()
    ret.tax_loss_offset_claimed = Decimal("450000")  # > 75% of 500,000 (=375,000)
    result = review_ct_return(ret)
    assert "CT-LOSS-001" in _ids(result)


# ── Transfer pricing & DMTT ──────────────────────────────────────────────────
def test_transfer_pricing_threshold():
    ret = _clean_return()
    ret.has_related_party_transactions = True
    ret.revenue = Decimal("250000000")  # ≥ 200M
    result = review_ct_return(ret)
    assert "CT-TP-001" in _ids(result)


def test_mne_member_gets_dmtt_info():
    ret = _clean_return()
    ret.is_mne_group_member = True
    result = review_ct_return(ret)
    assert "CT-DMTT-001" in _ids(result)


# ── Extraction gaps become verification items, not failures ──────────────────
def test_missing_fields_are_verification_not_failure():
    ret = CorporateTaxReturn(is_ct_registered=True)  # almost everything missing
    result = review_ct_return(ret)
    assert result.requires_verification
    assert len(result.verification_items) > 0
    # No present-data violations → must not FAIL purely from missing fields.
    assert result.compliance_status != ComplianceStatus.FAIL


# ── Legal references are marked provisional ──────────────────────────────────
def test_legal_refs_are_provisional():
    ret = _clean_return()
    ret.is_ct_registered = False  # guarantees at least one finding with a legal_ref
    result = review_ct_return(ret)
    refs = [f.legal_ref for f in result.findings if f.legal_ref]
    assert refs and all("PROVISIONAL" in r for r in refs)


# ── Computation engine (Phase C) ─────────────────────────────────────────────
def test_computation_bridge_profit_to_tax():
    ret = CorporateTaxReturn(
        accounting_net_profit=Decimal("1000000"),
        non_deductible_expenses=Decimal("50000"),      # +50,000
        entertainment_expense=Decimal("100000"),       # +50,000 disallowed (50%)
        exempt_income=Decimal("200000"),               # −200,000
        net_interest_expense=Decimal("0"),
        tax_ebitda=Decimal("100000"),                  # cap = max(12M, 30k) = 12M → no addback
    )
    comp = compute_ct(ret)
    # 1,000,000 + 50,000 + 50,000 − 200,000 = 900,000 taxable income
    assert comp.taxable_income == Decimal("900000.00")
    # 9% × (900,000 − 375,000) = 47,250
    assert comp.tax_before_credits == Decimal("47250.00")
    assert comp.ct_payable == Decimal("47250.00")
    # Trace is present and ends at CT payable.
    assert any(line.step == "ct_payable" for line in comp.lines)


def test_computation_foreign_tax_credit_capped():
    ret = CorporateTaxReturn(taxable_income=Decimal("475000"), foreign_tax_credit=Decimal("50000"))
    comp = compute_ct(ret)
    assert comp.tax_before_credits == Decimal("9000.00")   # 9% of 100,000
    assert comp.foreign_tax_credit == Decimal("9000.00")   # capped at the tax
    assert comp.ct_payable == Decimal("0.00")


def test_computation_interest_excess_added_back():
    ret = CorporateTaxReturn(
        accounting_net_profit=Decimal("20000000"),
        tax_ebitda=Decimal("10000000"),               # 30% = 3M; de minimis 12M wins
        net_interest_expense=Decimal("15000000"),     # excess 3M over 12M cap
    )
    comp = compute_ct(ret)
    assert comp.taxable_income == Decimal("23000000.00")  # 20M + 3M excess


def test_result_carries_computation_trace():
    result = review_ct_return(_clean_return())
    assert result.computation is not None
    assert result.computation.ct_payable == Decimal("11250")


# ── New §17 rules: TP disclosure & participation exemption ───────────────────
def test_tp_disclosure_schedule_threshold():
    ret = _clean_return()
    ret.related_party_transactions_total = Decimal("50000000")  # > AED 40M
    result = review_ct_return(ret)
    assert "CT-TP-002" in _ids(result)


def test_connected_person_disclosure_threshold():
    ret = _clean_return()
    ret.connected_person_payments_total = Decimal("750000")  # > AED 500k
    result = review_ct_return(ret)
    assert "CT-TP-002" in _ids(result)


def test_participation_exemption_conditions_not_met_fails():
    ret = _clean_return()
    ret.participation_exemption_claimed = True
    ret.participation_ownership_pct = Decimal("0.02")       # < 5%
    ret.participation_acquisition_cost = Decimal("1000000")  # ≤ AED 4M
    ret.participation_holding_months = 6                     # < 12
    result = review_ct_return(ret)
    assert "CT-EXM-001" in _ids(result)
    assert result.failed


def test_participation_exemption_conditions_met_passes():
    ret = _clean_return()
    ret.participation_exemption_claimed = True
    ret.participation_ownership_pct = Decimal("0.10")        # ≥ 5%
    ret.participation_holding_months = 24                    # ≥ 12
    ret.participation_subject_to_tax = True
    result = review_ct_return(ret)
    assert "CT-EXM-001" not in _ids(result)
