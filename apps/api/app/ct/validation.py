"""CT data validation & verification flagging.

Runs before the compliance rules. Missing / low-confidence fields become
`VerificationItem`s (manual-review flags) — they do NOT make the return non-compliant.
Cross-field sanity checks become `ValidationCheck`s. This mirrors the VAT philosophy:
an extraction gap is never a compliance failure.
"""

from __future__ import annotations

from ..compliance.domain import ValidationCheck, VerificationItem
from .schemas import CorporateTaxReturn

# Critical fields whose absence should be surfaced for manual verification.
_CRITICAL_FIELDS: list[tuple[str, str]] = [
    ("entity_name", "Entity name"),
    ("trn", "Tax Registration Number"),
    ("tax_period_end", "Tax period end date"),
    ("revenue", "Total revenue"),
    ("taxable_income", "Taxable income"),
    ("corporate_tax_payable", "Corporate tax payable"),
]


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_ct_return(
    ret: CorporateTaxReturn,
) -> tuple[list[VerificationItem], list[ValidationCheck]]:
    verification: list[VerificationItem] = []
    for field, label in _CRITICAL_FIELDS:
        if _blank(getattr(ret, field, None)):
            conf = ret.field_confidence.get(field, 0.0)
            verification.append(
                VerificationItem(
                    field=field,
                    label=label,
                    confidence=conf,
                    status="not_detected",
                    reason=f"{label} was not found in the extracted return.",
                    recommendation=f"Confirm {label.lower()} from the financial statements / CT computation.",
                )
            )

    checks: list[ValidationCheck] = []

    # Currency sanity: CT is assessed in AED.
    if ret.currency and ret.currency.upper() != "AED":
        checks.append(
            ValidationCheck(
                name="currency_is_aed",
                passed=False,
                detail=f"Return currency is '{ret.currency}'; UAE CT is assessed in AED.",
            )
        )

    # Taxable income should not exceed accounting profit by an unexplained margin (a
    # rough sanity signal only — legitimate add-backs can raise it).
    if ret.taxable_income is not None and ret.accounting_net_profit is not None:
        checks.append(
            ValidationCheck(
                name="taxable_income_vs_accounting_profit",
                passed=True,
                detail=(
                    f"Taxable income {ret.taxable_income} vs accounting net profit "
                    f"{ret.accounting_net_profit} (differences are expected from CT adjustments)."
                ),
            )
        )

    return verification, checks
