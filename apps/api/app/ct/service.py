"""Persistence & orchestration for Corporate Tax returns.

Runs the deterministic engine (`review_ct_return`) and stores immutable JSON snapshots of
both the return and the result, plus denormalised columns for dashboard/history queries —
mirroring the VAT `review_service` / `vat201.service` patterns.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CtReturnRecord
from . import constants as C
from .computation import _parse_date
from .rules import review_ct_return
from .schemas import CorporateTaxReturn, CTReviewResult


def _filing_due(period_end_iso: str | None) -> str | None:
    end = _parse_date(period_end_iso)
    if end is None:
        return None
    month = end.month - 1 + C.CT_RETURN_FILING_MONTHS
    year = end.year + month // 12
    return date(year, month % 12 + 1, 1).isoformat()


def _denormalise(rec: CtReturnRecord, ret: CorporateTaxReturn, result: CTReviewResult) -> None:
    rec.entity_name = ret.entity_name
    rec.trn = ret.trn
    rec.tax_period_start = ret.tax_period_start
    rec.tax_period_end = ret.tax_period_end
    rec.return_json = ret.model_dump(mode="json")
    rec.result_json = result.model_dump(mode="json")
    rec.compliance_status = result.compliance_status.value
    rec.risk_level = result.risk_level.value
    rec.taxable_income = (
        str(result.computation.taxable_income) if result.computation else None
    )
    rec.computed_tax = str(result.computed_tax) if result.computed_tax is not None else None


def create_ct_return(db: Session, ret: CorporateTaxReturn) -> tuple[CtReturnRecord, CTReviewResult]:
    result = review_ct_return(ret)
    rec = CtReturnRecord()
    _denormalise(rec, ret, result)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec, result


def revalidate(db: Session, rec: CtReturnRecord) -> CTReviewResult:
    """Re-run the engine on the stored return snapshot (e.g. after a rule/config change)."""
    ret = CorporateTaxReturn(**rec.return_json)
    result = review_ct_return(ret)
    _denormalise(rec, ret, result)
    db.commit()
    db.refresh(rec)
    return result


def update_return(
    db: Session, rec: CtReturnRecord, ret: CorporateTaxReturn
) -> CTReviewResult:
    result = review_ct_return(ret)
    _denormalise(rec, ret, result)
    db.commit()
    db.refresh(rec)
    return result


def dashboard(db: Session) -> dict:
    rows = list(db.execute(select(CtReturnRecord)).scalars())
    total_ct = Decimal("0")
    for r in rows:
        if r.computed_tax:
            try:
                total_ct += Decimal(r.computed_tax)
            except (ValueError, ArithmeticError):
                pass
    upcoming = []
    for r in rows:
        due = _filing_due(r.tax_period_end)
        if due and r.status not in ("filed", "closed"):
            upcoming.append({
                "id": r.id, "entity_name": r.entity_name,
                "tax_period_end": r.tax_period_end, "filing_due": due, "status": r.status,
            })
    upcoming.sort(key=lambda x: x["filing_due"])
    return {
        "total_returns": len(rows),
        "by_status": dict(Counter(r.status for r in rows)),
        "by_risk": dict(Counter(r.risk_level for r in rows)),
        "by_compliance": dict(Counter(r.compliance_status for r in rows)),
        "total_ct_payable": str(total_ct),
        "pending_reviews": sum(1 for r in rows if r.status in ("draft", "data_collection", "validation")),
        "high_risk": sum(1 for r in rows if r.risk_level == "high"),
        "upcoming_deadlines": upcoming[:20],
    }
