"""Classify transactions into VAT201 boxes and aggregate the return."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .schemas import (
    BOX_LABELS,
    EMIRATE_BOX,
    EXPENSE_BOXES,
    SALES_BOXES,
    BoxValue,
    Direction,
    Transaction,
    Treatment,
    Vat201Return,
    Vat201Totals,
)


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def classify_contributions(txn: Transaction) -> list[tuple[str, Decimal, Decimal]]:
    """Return the (box, taxable, vat) contributions for a transaction.

    Reverse-charge purchases and imports contribute to *two* boxes — the self-assessed
    output (sales side) and the recoverable input (expenses side) — which nets to zero
    when fully recoverable, exactly as the VAT201 mechanism intends.
    """
    t, v = txn.taxable_amount, txn.vat_amount
    d, tr = txn.direction, txn.treatment

    if d == Direction.SALE:
        if tr == Treatment.STANDARD:
            return [(EMIRATE_BOX.get(txn.emirate, "1b"), t, v)]
        if tr == Treatment.REVERSE_CHARGE:
            return [("3", t, v)]
        if tr == Treatment.ZERO_RATED:
            return [("4", t, Decimal(0))]
        if tr == Treatment.EXEMPT:
            return [("5", t, Decimal(0))]
        if tr == Treatment.IMPORT:
            return [("6", t, v), ("9", t, v)]
        return []

    if d == Direction.PURCHASE:
        if tr == Treatment.IMPORT:
            return [("6", t, v), ("9", t, v)]           # import due + recoverable
        if tr == Treatment.REVERSE_CHARGE:
            return [("3", t, v), ("10", t, v)]          # self-assessed output + recoverable
        if tr == Treatment.STANDARD:
            return [("9", t, v)]                          # recoverable input
        # zero-rated / exempt purchases carry no recoverable VAT
        return [("9", t, Decimal(0))]

    return []


def build_return(transactions: list[Transaction], base: Vat201Return) -> Vat201Return:
    """Aggregate classified transactions into the VAT201 boxes + totals."""
    box_amount: dict[str, Decimal] = {b: Decimal(0) for b in BOX_LABELS}
    box_vat: dict[str, Decimal] = {b: Decimal(0) for b in BOX_LABELS}
    box_count: dict[str, int] = {b: 0 for b in BOX_LABELS}

    for txn in transactions:
        contribs = classify_contributions(txn)
        txn.boxes = [b for b, _, _ in contribs]
        for box, taxable, vat in contribs:
            box_amount[box] += taxable
            box_vat[box] += vat
            box_count[box] += 1

    # Section subtotals.
    box_amount["8"] = sum((box_amount[b] for b in SALES_BOXES), Decimal(0))
    box_vat["8"] = sum((box_vat[b] for b in SALES_BOXES), Decimal(0))
    box_amount["11"] = sum((box_amount[b] for b in EXPENSE_BOXES), Decimal(0))
    box_vat["11"] = sum((box_vat[b] for b in EXPENSE_BOXES), Decimal(0))

    # Due / recoverable / net.
    box_vat["12"] = box_vat["8"]
    box_vat["13"] = box_vat["11"]
    net = box_vat["12"] - box_vat["13"]
    box_vat["14"] = net

    boxes = [
        BoxValue(box=b, label=BOX_LABELS[b], amount=_q(box_amount[b]), vat=_q(box_vat[b]), count=box_count[b])
        for b in BOX_LABELS
    ]

    rc_vat = box_vat["3"]
    base.boxes = boxes
    base.transaction_count = len(transactions)
    base.totals = Vat201Totals(
        total_sales_taxable=_q(box_amount["8"]),
        output_vat=_q(box_vat["12"]),
        reverse_charge_vat=_q(rc_vat),
        total_expenses_taxable=_q(box_amount["11"]),
        recoverable_input_vat=_q(box_vat["13"]),
        net_vat_due=_q(abs(net)),
        is_refund=net < 0,
    )
    return base
