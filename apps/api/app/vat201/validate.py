"""Pre-submission validation of the transaction set."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from .schemas import Direction, Transaction, Treatment, ValidationIssue

_TOL = Decimal("0.02")


def _valid_trn(trn: str | None) -> bool:
    if not trn:
        return False
    digits = "".join(ch for ch in str(trn) if ch.isdigit())
    return len(digits) == 15 and digits == str(trn).strip()


def validate_transactions(txns: list[Transaction]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def add(sev, code, msg, txn=None):
        issues.append(
            ValidationIssue(
                severity=sev, code=code, message=msg,
                row_index=getattr(txn, "row_index", None),
                invoice_number=getattr(txn, "invoice_number", None),
            )
        )

    # Duplicate sales invoice numbers.
    sale_invoices = [
        t.invoice_number for t in txns if t.direction == Direction.SALE and t.invoice_number
    ]
    dups = {inv for inv, n in Counter(sale_invoices).items() if n > 1}
    missing_emirate = 0

    for t in txns:
        if t.direction is None:
            add("error", "MISSING_DIRECTION", "Cannot tell if this is a sale or a purchase.", t)
        if t.treatment is None:
            add("error", "MISSING_TAX_CODE", "No VAT tax code / treatment could be determined.", t)
        if t.trn and not _valid_trn(t.trn):
            add("error", "INVALID_TRN", f"TRN '{t.trn}' is not a valid 15-digit number.", t)
        if t.taxable_amount < 0:
            add("warning", "NEGATIVE_VALUE", "Negative taxable value (credit/adjustment?) — verify.", t)
        if t.date is None:
            add("warning", "UNDATED", "Transaction has no readable date; period membership unverified.", t)

        if t.treatment == Treatment.STANDARD:
            if t.vat_rate is not None and abs(t.vat_rate - Decimal("0.05")) > Decimal("0.001"):
                add("error", "BAD_VAT_RATE", f"Standard-rated but rate is {t.vat_rate}, expected 5%.", t)
            expected = (t.taxable_amount * Decimal("0.05")).quantize(Decimal("0.01"))
            if t.vat_amount and abs(expected - t.vat_amount) > _TOL:
                add(
                    "warning", "VAT_MISMATCH",
                    f"VAT {t.vat_amount} ≠ 5% of {t.taxable_amount} ({expected}).", t,
                )
            if t.direction == Direction.SALE and t.emirate.value == "unallocated":
                missing_emirate += 1

        if t.invoice_number in dups and t.direction == Direction.SALE:
            add("warning", "DUPLICATE_INVOICE", f"Invoice number '{t.invoice_number}' appears more than once.", t)

        if t.treatment == Treatment.REVERSE_CHARGE and t.direction == Direction.SALE and t.vat_amount > 0:
            add(
                "warning", "RCM_TREATMENT",
                "Reverse-charge supply shows output VAT charged — the recipient should self-account.", t,
            )

    if missing_emirate:
        add(
            "warning", "MISSING_EMIRATE",
            f"{missing_emirate} standard-rated supply(ies) had no Emirate — reported under Dubai "
            "(Box 1b). Add an Emirate column to split Box 1 across emirates if required.",
        )

    return issues
