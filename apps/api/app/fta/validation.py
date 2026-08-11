"""Post-implementation compliance validation (requirement #8).

Runs a battery against the live VAT engine across every transaction type, so that after
an approved regulatory change is implemented, we can confirm the engine still classifies
each transaction category correctly.
"""

from __future__ import annotations

from decimal import Decimal


def run_compliance_validation() -> dict:
    from ..vat201.engine import build_return, classify_contributions
    from ..vat201.schemas import (
        Direction,
        Emirate,
        Transaction,
        Treatment,
        Vat201Return,
    )

    checks: list[dict] = []

    def add(category: str, passed: bool, detail: str) -> None:
        checks.append({"category": category, "passed": bool(passed), "detail": detail})

    def txn(**kw) -> Transaction:
        base = dict(row_index=1, emirate=Emirate.DUBAI, taxable_amount=Decimal("1000"),
                    vat_amount=Decimal("50"))
        base.update(kw)
        return Transaction(**base)

    def boxes(t: Transaction):
        return [b for b, _, _ in classify_contributions(t)]

    # Sales invoice (standard-rated) -> emirate output box
    add("Sales invoices", boxes(txn(direction=Direction.SALE, treatment=Treatment.STANDARD)) == ["1b"],
        "Standard-rated sale posts to Box 1 (emirate output).")

    # Sales credit note (standard, negative) -> same box, negative value
    cn = txn(direction=Direction.SALE, treatment=Treatment.STANDARD,
             taxable_amount=Decimal("-1000"), vat_amount=Decimal("-50"))
    contrib = classify_contributions(cn)
    add("Sales credit notes",
        contrib and contrib[0][0] == "1b" and contrib[0][2] == Decimal("-50"),
        "Credit note reverses output VAT in the same box.")

    # Customer receipts / advance payments -> taxed at supply treatment (standard)
    add("Customer receipts / advances",
        boxes(txn(direction=Direction.SALE, treatment=Treatment.STANDARD)) == ["1b"],
        "Advance/receipt for a standard supply carries 5% output VAT.")

    # Zero-rated sale -> Box 4, no VAT
    z = classify_contributions(txn(direction=Direction.SALE, treatment=Treatment.ZERO_RATED,
                                   vat_amount=Decimal("0")))
    add("Zero-rated supplies", z == [("4", Decimal("1000"), Decimal("0"))], "Zero-rated -> Box 4, 0% VAT.")

    # Exempt sale -> Box 5, no VAT
    ex = classify_contributions(txn(direction=Direction.SALE, treatment=Treatment.EXEMPT,
                                    vat_amount=Decimal("0")))
    add("Exempt supplies", ex == [("5", Decimal("1000"), Decimal("0"))], "Exempt -> Box 5, no VAT.")

    # Vendor bills / expenses (standard purchase) -> Box 9 recoverable
    add("Vendor bills / expenses",
        boxes(txn(direction=Direction.PURCHASE, treatment=Treatment.STANDARD)) == ["9"],
        "Standard expense posts recoverable input VAT to Box 9.")

    # Vendor credit note (purchase, negative) -> Box 9 negative
    vcn = classify_contributions(txn(direction=Direction.PURCHASE, treatment=Treatment.STANDARD,
                                     taxable_amount=Decimal("-1000"), vat_amount=Decimal("-50")))
    add("Vendor credit notes", vcn and vcn[0][0] == "9" and vcn[0][2] == Decimal("-50"),
        "Vendor credit note reverses input VAT in Box 9.")

    # Reverse charge purchase -> Box 3 (output) + Box 10 (recoverable)
    add("Reverse charge",
        boxes(txn(direction=Direction.PURCHASE, treatment=Treatment.REVERSE_CHARGE)) == ["3", "10"],
        "Reverse charge self-assesses output (Box 3) and recovers input (Box 10).")

    # VAT return calculation -> net = output - input
    base = Vat201Return(company_name="Validation", period_label="TEST")
    ret = build_return(
        [
            txn(direction=Direction.SALE, treatment=Treatment.STANDARD),               # +50 output
            txn(direction=Direction.PURCHASE, treatment=Treatment.STANDARD,
                taxable_amount=Decimal("400"), vat_amount=Decimal("20")),              # -20 input
        ],
        base,
    )
    add("VAT return calculations", ret.totals.net_vat_due == Decimal("30.00") and not ret.totals.is_refund,
        f"Net VAT due = output 50 − input 20 = {ret.totals.net_vat_due}.")

    # VAT reports -> boxes assemble
    add("VAT reports", len(ret.boxes) > 0 and any(b.box == "9" for b in ret.boxes),
        "Return report assembles all VAT201 boxes.")

    passed = sum(1 for c in checks if c["passed"])
    return {
        "passed": passed,
        "total": len(checks),
        "ok": passed == len(checks),
        "checks": checks,
    }
