"""Deterministic UAE Corporate Tax (CT) rule engine.

Each rule is a small pure function that inspects a normalised
:class:`CorporateTaxReturn` and yields zero or more :class:`Finding` objects. The
engine runs every rule, then derives an overall verdict from the findings' severities
(shared logic in :func:`app.compliance.domain.status_and_risk`).

Design mirrors the VAT engine (`app.vat.rules`):
  * verdicts are DETERMINISTIC and traceable to a (provisional) legal reference;
  * a *missing* field is an extraction gap → verification item, never a failure;
  * rules only fire on data that is actually present/asserted on the return.

⚠️  The rule set and its legal references are PROVISIONAL — a draft catalogue
(`docs/ct-compliance-brief.md`) pending UAE CT subject-matter-expert validation.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from ..compliance.domain import Finding, Severity, status_and_risk
from . import constants as C
from .computation import (
    _parse_date,
    _round,
    _sbr_eligible,
    compute_ct,
    expected_standard_tax,
)
from .schemas import CorporateTaxReturn, CTReviewResult, FreeZoneStatus, TaxpayerType


# ── Helpers ──────────────────────────────────────────────────────────────────
def _d(value: object) -> Decimal | None:
    return value if isinstance(value, Decimal) else None


def _valid_trn(trn: str | None) -> bool:
    if trn is None or str(trn).strip() == "":
        return False
    digits = "".join(ch for ch in str(trn) if ch.isdigit())
    return len(digits) == C.TRN_LENGTH and digits == str(trn).strip()


def registration_deadline(ret: CorporateTaxReturn) -> date | None:
    """Best-effort CT registration deadline (FTA Decision No. 3 of 2024).

    Resident juridical persons incorporated on/after 1 Mar 2024 get 3 months from
    incorporation; those before that date are driven by the month their licence was
    issued. Returns None when we lack the inputs to decide.
    """
    inc = _parse_date(ret.incorporation_date)
    if inc is not None and inc >= date(2024, 3, 1):
        # 3 months from incorporation (approximate month arithmetic).
        month = inc.month - 1 + C.REGISTRATION_WINDOW_MONTHS_NEW
        year = inc.year + month // 12
        month = month % 12 + 1
        # clamp day to the 1st for a conservative deadline
        return date(year, month, 1)
    if ret.licence_issue_month in C.REGISTRATION_DEADLINE_BY_LICENCE_MONTH:
        return _parse_date(C.REGISTRATION_DEADLINE_BY_LICENCE_MONTH[ret.licence_issue_month])
    return None


# `_sbr_eligible` and `expected_standard_tax` are the canonical calc helpers in
# `ct.computation`; imported above and re-exported here for backwards compatibility.


# ── Rules: registration & filing ─────────────────────────────────────────────
def rule_registration(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if ret.is_ct_registered is False:
        yield Finding(
            rule_id="CT-REG-001",
            severity=Severity.HIGH,
            title="Entity is not registered for Corporate Tax",
            detail=(
                "Every taxable person must register for CT and obtain a Tax Registration "
                "Number. This entity is marked as not registered."
            ),
            legal_ref=C.LEGAL_REFS["registration"],
            recommendation="Register via EmaraTax without delay to limit penalty exposure.",
        )


def rule_registration_deadline(ret: CorporateTaxReturn) -> Iterator[Finding]:
    deadline = registration_deadline(ret)
    reg = _parse_date(ret.registration_date)
    if deadline is not None and reg is not None and reg > deadline:
        yield Finding(
            rule_id="CT-REG-002",
            severity=Severity.HIGH,
            title="Corporate Tax registration was late",
            detail=(
                f"Registered on {reg.isoformat()}, after the applicable deadline of "
                f"{deadline.isoformat()}. Late registration carries an administrative "
                f"penalty of AED {C.LATE_REGISTRATION_PENALTY_AED:,}."
            ),
            legal_ref=C.LEGAL_REFS["late_registration_penalty"],
            recommendation=(
                "Check whether the FTA penalty-waiver applies (first return filed within "
                "7 months of the first tax period end)."
            ),
        )


def rule_filing_deadline(ret: CorporateTaxReturn) -> Iterator[Finding]:
    period_end = _parse_date(ret.tax_period_end)
    filing = _parse_date(ret.filing_date)
    if period_end is None or filing is None:
        return
    # Due within 9 months of period end (approximate month arithmetic).
    month = period_end.month - 1 + C.CT_RETURN_FILING_MONTHS
    year = period_end.year + month // 12
    due = date(year, month % 12 + 1, 1)
    if filing >= due:
        yield Finding(
            rule_id="CT-FILE-001",
            severity=Severity.HIGH,
            title="Corporate Tax return filed after the deadline",
            detail=(
                f"The return was filed {filing.isoformat()}, on/after the due date "
                f"(~{due.isoformat()}, i.e. 9 months after period end {period_end.isoformat()})."
            ),
            legal_ref=C.LEGAL_REFS["filing"],
            recommendation="File and pay within 9 months of the tax-period end.",
        )


# ── Rules: Small Business Relief ─────────────────────────────────────────────
def rule_sbr_available(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if not ret.elects_small_business_relief and _sbr_eligible(ret):
        yield Finding(
            rule_id="CT-SBR-001",
            severity=Severity.INFO,
            title="Small Business Relief appears available",
            detail=(
                "Revenue is within the AED 3,000,000 ceiling and the period ends on/before "
                "31 Dec 2026, so the entity may elect Small Business Relief (treated as no "
                "taxable income, simplified compliance)."
            ),
            legal_ref=C.LEGAL_REFS["small_business_relief"],
            recommendation="Consider electing SBR if it is beneficial; the election is annual.",
        )


def rule_sbr_ineligible_status(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if not ret.elects_small_business_relief:
        return
    if ret.is_qfzp or ret.is_mne_group_member:
        who = "a Qualifying Free Zone Person" if ret.is_qfzp else "a member of an MNE Group"
        yield Finding(
            rule_id="CT-SBR-002",
            severity=Severity.MEDIUM,
            title="Small Business Relief elected but entity is ineligible",
            detail=(
                f"SBR is not available to {who}. The election is invalid and taxable income "
                "must be computed normally."
            ),
            legal_ref=C.LEGAL_REFS["small_business_relief"],
            recommendation="Withdraw the SBR election and compute CT on taxable income.",
        )


def rule_sbr_over_threshold(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if not ret.elects_small_business_relief:
        return
    if ret.revenue is not None and ret.revenue > Decimal(str(C.SBR_REVENUE_MAX)):
        yield Finding(
            rule_id="CT-SBR-003",
            severity=Severity.HIGH,
            title="Small Business Relief elected but revenue exceeds AED 3,000,000",
            detail=(
                f"Revenue of AED {ret.revenue:,} exceeds the SBR ceiling of "
                f"AED {C.SBR_REVENUE_MAX:,}. SBR cannot apply and tax would be understated."
            ),
            legal_ref=C.LEGAL_REFS["small_business_relief"],
            recommendation="Compute CT on taxable income; do not apply SBR.",
        )
    period_end = _parse_date(ret.tax_period_end)
    sunset = _parse_date(C.SBR_SUNSET_DATE)
    if period_end is not None and sunset is not None and period_end > sunset:
        yield Finding(
            rule_id="CT-SBR-004",
            severity=Severity.MEDIUM,
            title="Small Business Relief elected for a period after the sunset date",
            detail=(
                f"SBR only applies to tax periods ending on/before {C.SBR_SUNSET_DATE}; this "
                f"period ends {period_end.isoformat()}."
            ),
            legal_ref=C.LEGAL_REFS["small_business_relief"],
            recommendation="SBR is no longer available for this period; compute CT normally.",
        )


# ── Rules: rate / tax computation ────────────────────────────────────────────
def rule_rate_computation(ret: CorporateTaxReturn) -> Iterator[Finding]:
    # Only meaningful for a standard taxable person with both figures present, where no
    # 0%-regime (SBR applied & eligible, or QFZP qualifying income) is in play.
    if ret.taxable_income is None or ret.corporate_tax_payable is None:
        return
    if ret.is_qfzp:
        return  # QFZP qualifying income is 0%-rated — handled by the Free Zone rules
    if ret.elects_small_business_relief and _sbr_eligible(ret):
        # SBR: treated as no taxable income → expected tax 0.
        if ret.corporate_tax_payable > Decimal(str(C.CALC_TOLERANCE_AED)):
            yield Finding(
                rule_id="CT-RATE-002",
                severity=Severity.MEDIUM,
                title="Tax charged despite valid Small Business Relief",
                detail=(
                    f"SBR applies (no taxable income) yet CT payable is stated as "
                    f"AED {ret.corporate_tax_payable:,}."
                ),
                legal_ref=C.LEGAL_REFS["small_business_relief"],
                recommendation="Under SBR the tax payable should be nil.",
            )
        return
    expected = expected_standard_tax(ret.taxable_income)
    if abs(expected - ret.corporate_tax_payable) > Decimal(str(C.CALC_TOLERANCE_AED)):
        yield Finding(
            rule_id="CT-RATE-001",
            severity=Severity.HIGH,
            title="Corporate tax does not match the 0% / 9% rate bands",
            detail=(
                f"Expected CT on taxable income AED {ret.taxable_income:,} is "
                f"AED {expected:,} (0% up to AED {C.SMALL_PROFITS_THRESHOLD:,}, 9% above); "
                f"the return states AED {ret.corporate_tax_payable:,}."
            ),
            legal_ref=C.LEGAL_REFS["rates"],
            recommendation="Recompute: 9% × (taxable income − AED 375,000), floored at zero.",
        )


# ── Rules: Free Zone (QFZP) ──────────────────────────────────────────────────
def rule_qfzp_de_minimis(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if not ret.is_qfzp:
        return
    if ret.non_qualifying_revenue is None or ret.revenue is None or ret.revenue == 0:
        return
    cap = min(
        Decimal(str(C.QFZP_DE_MINIMIS_ABS)),
        ret.revenue * Decimal(str(C.QFZP_DE_MINIMIS_PCT)),
    )
    if ret.non_qualifying_revenue > cap:
        yield Finding(
            rule_id="CT-FZ-001",
            severity=Severity.HIGH,
            title="QFZP de minimis breached",
            detail=(
                f"Non-qualifying revenue AED {ret.non_qualifying_revenue:,} exceeds the de "
                f"minimis cap of AED {_round(cap):,} (lower of AED 5,000,000 or 5% of total "
                "revenue). QFZP status is lost for this period and the following four."
            ),
            legal_ref=C.LEGAL_REFS["free_zone_de_minimis"],
            recommendation="Reassess QFZP status; all taxable income would be taxed at 9%.",
        )


def rule_qfzp_audited_fs(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if ret.is_qfzp and ret.has_audited_financials is False:
        yield Finding(
            rule_id="CT-FZ-002",
            severity=Severity.MEDIUM,
            title="QFZP without audited financial statements",
            detail=(
                "Maintaining audited financial statements is a condition of Qualifying Free "
                "Zone Person status; the return indicates none are held."
            ),
            legal_ref=C.LEGAL_REFS["free_zone_audited_fs"],
            recommendation="Obtain audited financial statements to preserve QFZP status.",
        )


# ── Rules: deduction limitations ─────────────────────────────────────────────
def rule_interest_limitation(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if ret.net_interest_expense is None or ret.tax_ebitda is None:
        return
    de_minimis = Decimal(str(C.INTEREST_DE_MINIMIS))
    cap = max(de_minimis, ret.tax_ebitda * Decimal(str(C.INTEREST_EBITDA_PCT)))
    if ret.net_interest_expense > cap:
        yield Finding(
            rule_id="CT-INT-001",
            severity=Severity.MEDIUM,
            title="Net interest expense exceeds the deduction limit",
            detail=(
                f"Net interest expense AED {ret.net_interest_expense:,} exceeds the "
                f"deductible cap of AED {_round(cap):,} (higher of AED 12,000,000 or 30% of "
                f"tax-EBITDA AED {ret.tax_ebitda:,}). The excess is disallowed this period."
            ),
            legal_ref=C.LEGAL_REFS["interest_limitation"],
            recommendation="Disallow the excess (carry forward up to 10 years).",
        )


def rule_entertainment(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if ret.entertainment_expense is None or ret.entertainment_deduction_claimed is None:
        return
    allowed = _round(ret.entertainment_expense * Decimal(str(C.ENTERTAINMENT_DEDUCTIBLE_PCT)))
    if ret.entertainment_deduction_claimed > allowed + Decimal(str(C.CALC_TOLERANCE_AED)):
        yield Finding(
            rule_id="CT-ENT-001",
            severity=Severity.LOW,
            title="Entertainment deduction exceeds 50%",
            detail=(
                f"Claimed entertainment deduction AED {ret.entertainment_deduction_claimed:,} "
                f"exceeds 50% of entertainment expenditure (AED {allowed:,})."
            ),
            legal_ref=C.LEGAL_REFS["entertainment"],
            recommendation="Restrict the entertainment deduction to 50% of the expenditure.",
        )


def rule_loss_offset(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if ret.tax_loss_offset_claimed is None or ret.taxable_income is None or ret.taxable_income <= 0:
        return
    cap = _round(ret.taxable_income * Decimal(str(C.LOSS_OFFSET_MAX_PCT)))
    if ret.tax_loss_offset_claimed > cap + Decimal(str(C.CALC_TOLERANCE_AED)):
        yield Finding(
            rule_id="CT-LOSS-001",
            severity=Severity.MEDIUM,
            title="Tax-loss offset exceeds 75% of taxable income",
            detail=(
                f"Loss offset claimed AED {ret.tax_loss_offset_claimed:,} exceeds 75% of "
                f"taxable income (cap AED {cap:,})."
            ),
            legal_ref=C.LEGAL_REFS["tax_losses"],
            recommendation="Limit the offset to 75% of taxable income; carry the balance forward.",
        )


# ── Rules: transfer pricing & audited FS ─────────────────────────────────────
def rule_transfer_pricing(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if ret.has_related_party_transactions is not True:
        return
    over_taxpayer = (
        ret.revenue is not None
        and ret.revenue >= Decimal(str(C.TP_LOCAL_FILE_TAXPAYER_REVENUE))
    )
    if over_taxpayer or ret.is_mne_group_member:
        yield Finding(
            rule_id="CT-TP-001",
            severity=Severity.MEDIUM,
            title="Transfer-pricing documentation likely required",
            detail=(
                "The entity has related-party transactions and meets a documentation "
                "threshold (taxpayer revenue ≥ AED 200M or an MNE group). A master file and "
                "local file, plus the related-party disclosure, are likely required."
            ),
            legal_ref=C.LEGAL_REFS["transfer_pricing"],
            recommendation="Prepare/retain master & local files and file the TP disclosure.",
        )


def rule_tp_disclosure(ret: CorporateTaxReturn) -> Iterator[Finding]:
    """Return-disclosure schedule (distinct from master/local file): filed WITH the return
    when related-party or connected-person aggregates exceed the thresholds."""
    triggers: list[str] = []
    rp = ret.related_party_transactions_total
    cp = ret.connected_person_payments_total
    if rp is not None and rp > Decimal(str(C.TP_RP_DISCLOSURE_AGGREGATE)):
        triggers.append(
            f"related-party transactions of AED {rp:,} exceed AED {C.TP_RP_DISCLOSURE_AGGREGATE:,}"
        )
    if cp is not None and cp > Decimal(str(C.TP_CONNECTED_DISCLOSURE)):
        triggers.append(
            f"connected-person payments of AED {cp:,} exceed AED {C.TP_CONNECTED_DISCLOSURE:,}"
        )
    if triggers:
        yield Finding(
            rule_id="CT-TP-002",
            severity=Severity.MEDIUM,
            title="Transfer-pricing disclosure schedule required with the return",
            detail=(
                "A related-party / connected-person disclosure schedule must be filed with "
                "the CT return: " + "; ".join(triggers) + "."
            ),
            legal_ref=C.LEGAL_REFS["tp_disclosure"],
            recommendation="Complete the related-party / connected-persons schedule in the CT return.",
        )


def rule_participation_exemption(ret: CorporateTaxReturn) -> Iterator[Finding]:
    """Where the participation exemption (Art. 23) is claimed, its conditions must hold:
    ≥5% ownership OR acquisition cost > AED 4M; 12-month holding; subject-to-tax ≥9%."""
    if not ret.participation_exemption_claimed:
        return
    fails: list[str] = []
    own = ret.participation_ownership_pct
    cost = ret.participation_acquisition_cost
    own_ok = own is not None and own >= Decimal(str(C.PARTICIPATION_MIN_OWNERSHIP_PCT))
    cost_ok = cost is not None and cost > Decimal(str(C.PARTICIPATION_MIN_ACQUISITION_COST))
    if not (own_ok or cost_ok):
        fails.append(
            f"neither ≥{int(C.PARTICIPATION_MIN_OWNERSHIP_PCT * 100)}% ownership nor acquisition "
            f"cost > AED {C.PARTICIPATION_MIN_ACQUISITION_COST:,}"
        )
    if (
        ret.participation_holding_months is not None
        and ret.participation_holding_months < C.PARTICIPATION_MIN_HOLDING_MONTHS
    ):
        fails.append(
            f"holding period {ret.participation_holding_months} months < "
            f"{C.PARTICIPATION_MIN_HOLDING_MONTHS} months"
        )
    if ret.participation_subject_to_tax is False:
        fails.append("participation not subject to tax at ≥ 9%")
    if fails:
        yield Finding(
            rule_id="CT-EXM-001",
            severity=Severity.HIGH,
            title="Participation exemption claimed but conditions not met",
            detail="The participation exemption was claimed but: " + "; ".join(fails) + ".",
            legal_ref=C.LEGAL_REFS["participation_exemption"],
            recommendation=(
                "Confirm ≥5% ownership or acquisition cost > AED 4M, a 12-month holding "
                "period, and that the participation is subject to tax at ≥ 9%."
            ),
        )


def rule_audited_financials(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if (
        ret.revenue is not None
        and ret.revenue > Decimal(str(C.AUDITED_FS_REVENUE_THRESHOLD))
        and ret.has_audited_financials is False
    ):
        yield Finding(
            rule_id="CT-AUDIT-001",
            severity=Severity.MEDIUM,
            title="Audited financial statements required",
            detail=(
                f"Revenue AED {ret.revenue:,} exceeds AED "
                f"{C.AUDITED_FS_REVENUE_THRESHOLD:,}, so audited financial statements are "
                "required; the return indicates none are held."
            ),
            legal_ref=C.LEGAL_REFS["audited_financials"],
            recommendation="Obtain audited financial statements for the tax period.",
        )


def rule_dmtt_scope(ret: CorporateTaxReturn) -> Iterator[Finding]:
    if ret.is_mne_group_member:
        yield Finding(
            rule_id="CT-DMTT-001",
            severity=Severity.INFO,
            title="Potentially within scope of the 15% Domestic Minimum Top-up Tax",
            detail=(
                "As a member of an MNE group (global revenue ≥ EUR 750M), the entity may be "
                "subject to the 15% DMTT for financial years starting on/after 1 Jan 2025 — a "
                "separate computation and return."
            ),
            legal_ref=C.LEGAL_REFS["dmtt"],
            recommendation="Assess Pillar Two / DMTT obligations separately from standard CT.",
        )


# ── Registry & engine ────────────────────────────────────────────────────────
ALL_RULES = [
    rule_registration,
    rule_registration_deadline,
    rule_filing_deadline,
    rule_sbr_available,
    rule_sbr_ineligible_status,
    rule_sbr_over_threshold,
    rule_rate_computation,
    rule_qfzp_de_minimis,
    rule_qfzp_audited_fs,
    rule_interest_limitation,
    rule_entertainment,
    rule_loss_offset,
    rule_participation_exemption,
    rule_transfer_pricing,
    rule_tp_disclosure,
    rule_audited_financials,
    rule_dmtt_scope,
]


def review_ct_return(ret: CorporateTaxReturn) -> CTReviewResult:
    """Validate the CT return, flag verification gaps, run the deterministic rules and the
    traceable computation engine, then derive the verdict. Pass/Fail comes ONLY from
    compliance findings, never from extraction gaps (surfaced as verification items)."""
    from .validation import validate_ct_return

    verification_items, validations = validate_ct_return(ret)

    findings: list[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(ret))

    status, risk = status_and_risk(findings)
    highs = sum(1 for f in findings if f.severity == Severity.HIGH)
    meds = sum(1 for f in findings if f.severity == Severity.MEDIUM)
    lows = sum(1 for f in findings if f.severity == Severity.LOW)
    requires_verification = len(verification_items) > 0

    # Traceable profit→tax computation (also yields computed tax + effective rate).
    computation = compute_ct(ret)
    has_result = any(line.step in ("ct_payable", "sbr") for line in computation.lines)
    computed_tax = computation.ct_payable if has_result else None
    effective_rate = computation.effective_rate if has_result else None

    verify_note = (
        f" · {len(verification_items)} field(s) require verification" if requires_verification else ""
    )
    summary = (
        f"CT compliance {status.value.upper()} · risk {risk.value.upper()} · "
        f"{highs} high, {meds} medium, {lows} low finding(s){verify_note}."
    )

    return CTReviewResult(
        compliance_status=status,
        risk_level=risk,
        findings=findings,
        verification_items=verification_items,
        validations=validations,
        requires_verification=requires_verification,
        taxpayer_type=ret.taxpayer_type,
        free_zone_status=ret.free_zone_status,
        small_business_relief_applied=computation.small_business_relief_applied,
        computed_tax=computed_tax,
        effective_rate=effective_rate,
        computation=computation,
        summary=summary,
    )
