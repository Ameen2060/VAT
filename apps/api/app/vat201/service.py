"""Build + persist a VAT201 return from an uploaded transactions file."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import Vat201ReturnRecord, Vat201TxnRecord
from .engine import build_return
from .importer import parse_emirate, parse_transactions
from .schemas import Vat201Return
from .validate import validate_transactions


def _last_day(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def compute_period(period_type: str, year: int, index: int) -> tuple[date, date, str, date]:
    """Return (start, end, label, due_date). VAT201 is due within 28 days of period end."""
    if period_type == "month":
        start = date(year, index, 1)
        end = _last_day(year, index)
        label = f"{year}-{index:02d}"
    else:  # quarter
        start_month = (index - 1) * 3 + 1
        start = date(year, start_month, 1)
        end = _last_day(year, start_month + 2)
        label = f"{year}-Q{index}"
    return start, end, label, end + timedelta(days=28)


def generate_return(
    db: Session,
    *,
    filename: str,
    data: bytes,
    company_name: str | None,
    company_trn: str | None,
    period_type: str,
    year: int,
    index: int,
    filter_by_date: bool = True,
    default_emirate: str | None = None,
) -> Vat201ReturnRecord:
    start, end, label, due = compute_period(period_type, year, index)
    # When filtering is off (e.g. a pre-prepared workbook that already contains exactly
    # the period's rows, incl. staggered quarters like Jun–Aug), include every row.
    bounds = (start, end) if filter_by_date else (None, None)
    txns, _mapping = parse_transactions(
        filename, data, bounds[0], bounds[1], default_emirate=parse_emirate(default_emirate)
    )
    validations = validate_transactions(txns)

    ret = Vat201Return(
        company_name=company_name,
        company_trn=company_trn,
        period_type=period_type,
        period_label=label,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        due_date=due.isoformat(),
    )
    build_return(txns, ret)
    ret.validations = validations

    rec = Vat201ReturnRecord(
        company_name=company_name,
        company_trn=company_trn,
        period_type=period_type,
        period_label=label,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        due_date=due.isoformat(),
        net_vat_due=str(ret.totals.net_vat_due),
        is_refund=ret.totals.is_refund,
        return_json=ret.model_dump(mode="json"),
    )
    db.add(rec)
    db.flush()
    for t in txns:
        db.add(
            Vat201TxnRecord(
                return_id=rec.id,
                row_index=t.row_index,
                date=t.date,
                doc_type=t.doc_type,
                direction=t.direction.value if t.direction else None,
                party=t.party,
                trn=t.trn,
                invoice_number=t.invoice_number,
                emirate=t.emirate.value,
                treatment=t.treatment.value if t.treatment else None,
                taxable_amount=str(t.taxable_amount),
                vat_amount=str(t.vat_amount),
                boxes=t.boxes,
            )
        )
    db.commit()
    db.refresh(rec)
    return rec
