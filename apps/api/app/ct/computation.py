"""UAE Corporate Tax computation engine.

Builds a deterministic, **traceable** profit→tax computation: accounting net profit →
adjustments (add-backs / exempt income) → taxable income → loss relief → rate bands →
foreign tax credit → CT payable. Every step is emitted as a `ComputationLine` carrying its
amount, kind, and (where relevant) legal reference, so the result is auditable end to end.

This module owns the low-level calc helpers (`expected_standard_tax`, `_sbr_eligible`,
`_round`, `_parse_date`); `ct/rules.py` imports them from here (one-way dependency —
computation never imports rules).

⚠️  Rates/thresholds are PROVISIONAL pending SME validation (see docs/ct-knowledge-model.md §20).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from . import constants as C
from .schemas import ComputationLine, CorporateTaxReturn, CTComputation


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_date(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        return date.fromisoformat(iso[:10])
    except (ValueError, TypeError):
        return None


def expected_standard_tax(taxable_income: Decimal) -> Decimal:
    """Standard CT on a taxable-income figure: 0% up to the threshold, 9% above."""
    threshold = Decimal(str(C.SMALL_PROFITS_THRESHOLD))
    excess = taxable_income - threshold
    if excess <= 0:
        return Decimal("0")
    return _round(excess * Decimal(str(C.STANDARD_CT_RATE)))


def _sbr_eligible(ret: CorporateTaxReturn) -> bool:
    """Whether Small Business Relief is available (ignoring whether it was elected)."""
    if ret.is_qfzp or ret.is_mne_group_member:
        return False
    if ret.revenue is not None and ret.revenue > Decimal(str(C.SBR_REVENUE_MAX)):
        return False
    period_end = _parse_date(ret.tax_period_end)
    sunset = _parse_date(C.SBR_SUNSET_DATE)
    if period_end is not None and sunset is not None and period_end > sunset:
        return False
    return True


def _interest_cap(ret: CorporateTaxReturn) -> Decimal | None:
    if ret.tax_ebitda is None:
        return None
    return max(
        Decimal(str(C.INTEREST_DE_MINIMIS)),
        ret.tax_ebitda * Decimal(str(C.INTEREST_EBITDA_PCT)),
    )


def compute_ct(ret: CorporateTaxReturn) -> CTComputation:
    """Produce a traceable CT computation. Resilient to missing inputs: builds the full
    bridge from accounting profit when the adjustment inputs are present, otherwise starts
    from a provided taxable income; always applies the rate bands and foreign tax credit."""
    lines: list[ComputationLine] = []
    notes: list[str] = []
    qfzp = ret.is_qfzp

    # Small Business Relief short-circuits the whole computation to nil.
    if ret.elects_small_business_relief and _sbr_eligible(ret):
        if ret.accounting_net_profit is not None:
            lines.append(ComputationLine(
                step="accounting_profit", label="Accounting net profit",
                amount=_round(ret.accounting_net_profit), kind="base"))
        lines.append(ComputationLine(
            step="sbr", label="Small Business Relief — treated as nil taxable income",
            amount=Decimal("0"), kind="total", legal_ref=C.LEGAL_REFS["small_business_relief"]))
        return CTComputation(
            lines=lines, taxable_income=Decimal("0"), tax_before_credits=Decimal("0"),
            foreign_tax_credit=Decimal("0"), ct_payable=Decimal("0"),
            effective_rate=Decimal("0"), small_business_relief_applied=True, qfzp=qfzp,
            notes=["Small Business Relief applied → nil Corporate Tax."])

    # ── Build the bridge to adjusted taxable income ──
    if ret.accounting_net_profit is not None:
        running = ret.accounting_net_profit
        lines.append(ComputationLine(
            step="accounting_profit", label="Accounting net profit (IFRS)",
            amount=_round(running), kind="base", legal_ref=C.LEGAL_REFS["rates"]))

        if ret.non_deductible_expenses:
            running += ret.non_deductible_expenses
            lines.append(ComputationLine(
                step="non_deductible", label="Add: non-deductible expenditure",
                amount=_round(ret.non_deductible_expenses), kind="addback",
                legal_ref="Art. 33, Federal Decree-Law No. 47 of 2022 · PROVISIONAL"))

        if ret.entertainment_expense is not None:
            disallowed = ret.entertainment_expense * (Decimal("1") - Decimal(str(C.ENTERTAINMENT_DEDUCTIBLE_PCT)))
            if disallowed > 0:
                running += disallowed
                lines.append(ComputationLine(
                    step="entertainment", label="Add: 50% of entertainment expenditure (disallowed)",
                    amount=_round(disallowed), kind="addback", legal_ref=C.LEGAL_REFS["entertainment"]))

        cap = _interest_cap(ret)
        if cap is not None and ret.net_interest_expense is not None:
            excess = ret.net_interest_expense - cap
            if excess > 0:
                running += excess
                lines.append(ComputationLine(
                    step="interest_excess", label="Add: net interest above the deduction cap",
                    amount=_round(excess), kind="addback", legal_ref=C.LEGAL_REFS["interest_limitation"]))
                notes.append("Excess interest carries forward up to 10 tax periods.")

        if ret.exempt_income:
            running -= ret.exempt_income
            lines.append(ComputationLine(
                step="exempt_income", label="Less: exempt income (dividends / participation)",
                amount=_round(-ret.exempt_income), kind="deduction",
                legal_ref="Art. 22-23, Federal Decree-Law No. 47 of 2022 · PROVISIONAL"))

        adjusted = running
        lines.append(ComputationLine(
            step="adjusted", label="Adjusted taxable income (pre-loss relief)",
            amount=_round(adjusted), kind="subtotal"))
    elif ret.taxable_income is not None:
        adjusted = ret.taxable_income
        lines.append(ComputationLine(
            step="taxable_income_input", label="Taxable income (as provided)",
            amount=_round(adjusted), kind="base"))
    else:
        return CTComputation(
            lines=lines, notes=["Insufficient data to compute taxable income "
                                "(need accounting net profit or taxable income)."], qfzp=qfzp)

    # ── Loss relief (≤ 75% of taxable income) ──
    loss_claimed = ret.tax_loss_offset_claimed or Decimal("0")
    if loss_claimed > 0 and adjusted > 0:
        cap75 = adjusted * Decimal(str(C.LOSS_OFFSET_MAX_PCT))
        applied = min(loss_claimed, cap75)
        taxable_income = adjusted - applied
        lines.append(ComputationLine(
            step="loss_offset", label="Less: tax loss offset (max 75%)",
            amount=_round(-applied), kind="deduction", legal_ref=C.LEGAL_REFS["tax_losses"]))
        if loss_claimed > cap75:
            notes.append("Tax-loss offset capped at 75% of taxable income; balance carried forward.")
    else:
        taxable_income = adjusted

    lines.append(ComputationLine(
        step="taxable_income", label="Taxable income", amount=_round(taxable_income), kind="subtotal"))

    # ── Rate bands ──
    positive_ti = taxable_income if taxable_income > 0 else Decimal("0")
    tax_before = expected_standard_tax(positive_ti)
    if qfzp:
        notes.append("QFZP: qualifying income is 0%-rated; the figure below applies the "
                     "standard bands to total taxable income and must be adjusted for the "
                     "qualifying/non-qualifying split.")
    lines.append(ComputationLine(
        step="tax_before_credits", label="Corporate tax (0% ≤ AED 375,000; 9% above)",
        amount=_round(tax_before), kind="tax", legal_ref=C.LEGAL_REFS["rates"]))

    # ── Foreign tax credit ──
    ftc = ret.foreign_tax_credit or Decimal("0")
    ftc_applied = min(ftc, tax_before) if ftc > 0 else Decimal("0")
    if ftc_applied > 0:
        lines.append(ComputationLine(
            step="ftc", label="Less: foreign tax credit (capped at UAE CT on that income)",
            amount=_round(-ftc_applied), kind="credit", legal_ref=C.LEGAL_REFS["foreign_tax_credit"]))
        if ftc > ftc_applied:
            notes.append("Foreign tax credit is capped at the UAE CT on the same income; excess is lost.")

    ct_payable = tax_before - ftc_applied
    lines.append(ComputationLine(
        step="ct_payable", label="Corporate Tax payable", amount=_round(ct_payable), kind="total"))

    effective_rate = None
    if positive_ti > 0:
        effective_rate = (_round(ct_payable / positive_ti * Decimal("10000")) / Decimal("10000"))

    return CTComputation(
        lines=lines, taxable_income=_round(taxable_income), tax_before_credits=_round(tax_before),
        foreign_tax_credit=_round(ftc_applied), ct_payable=_round(ct_payable),
        effective_rate=effective_rate, small_business_relief_applied=False, qfzp=qfzp, notes=notes)
