"""Corporate Tax (CT) API — create/list/get/update CT returns, run the deterministic
rule + computation engine, view the traceable computation, a simple workflow status, and
dashboard aggregates.

⚠️  CT verdicts are PROVISIONAL pending SME validation (see docs/ct-knowledge-model.md §20).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..ct.computation import compute_ct
from ..ct.schemas import CorporateTaxReturn
from ..ct.service import create_ct_return, dashboard, revalidate, update_return
from ..models import CtReturnRecord

router = APIRouter(prefix="/api/ct", tags=["corporate-tax"])

# Workflow states (full state-machine with RBAC gating arrives in Phase D).
WORKFLOW_STATES = [
    "draft", "data_collection", "validation", "internal_review", "tax_review",
    "management_approval", "ready_for_filing", "filed", "under_fta_review", "closed",
]


class CtReturnSummary(BaseModel):
    id: str
    entity_name: str | None
    trn: str | None
    tax_period_start: str | None
    tax_period_end: str | None
    compliance_status: str
    risk_level: str
    taxable_income: str | None
    computed_tax: str | None
    status: str
    created_at: str | None


def _summary(r: CtReturnRecord) -> CtReturnSummary:
    return CtReturnSummary(
        id=r.id, entity_name=r.entity_name, trn=r.trn,
        tax_period_start=r.tax_period_start, tax_period_end=r.tax_period_end,
        compliance_status=r.compliance_status, risk_level=r.risk_level,
        taxable_income=r.taxable_income, computed_tax=r.computed_tax, status=r.status,
        created_at=r.created_at.isoformat() if r.created_at else None,
    )


def _get(db: Session, return_id: str) -> CtReturnRecord:
    rec = db.get(CtReturnRecord, return_id)
    if not rec:
        raise HTTPException(status_code=404, detail="CT return not found")
    return rec


@router.post("/returns")
def create_return(payload: CorporateTaxReturn, db: Session = Depends(get_db)) -> dict:
    """Create a CT return, run the rule + computation engine, and persist a snapshot."""
    rec, result = create_ct_return(db, payload)
    return {"id": rec.id, "status": rec.status, "result": result.model_dump(mode="json")}


@router.get("/returns", response_model=list[CtReturnSummary])
def list_returns(
    risk: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[CtReturnSummary]:
    stmt = select(CtReturnRecord).order_by(CtReturnRecord.created_at.desc())
    if risk:
        stmt = stmt.where(CtReturnRecord.risk_level == risk)
    if status:
        stmt = stmt.where(CtReturnRecord.status == status)
    return [_summary(r) for r in db.execute(stmt).scalars()]


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> dict:
    return dashboard(db)


@router.get("/returns/{return_id}")
def get_return(return_id: str, db: Session = Depends(get_db)) -> dict:
    rec = _get(db, return_id)
    return {
        "id": rec.id, "status": rec.status,
        "return": rec.return_json, "result": rec.result_json,
    }


@router.patch("/returns/{return_id}")
def patch_return(return_id: str, payload: CorporateTaxReturn, db: Session = Depends(get_db)) -> dict:
    rec = _get(db, return_id)
    result = update_return(db, rec, payload)
    return {"id": rec.id, "status": rec.status, "result": result.model_dump(mode="json")}


@router.post("/returns/{return_id}/validate")
def validate_return(return_id: str, db: Session = Depends(get_db)) -> dict:
    """Re-run the engine on the stored return (e.g. after a rule/config change)."""
    rec = _get(db, return_id)
    result = revalidate(db, rec)
    return {"id": rec.id, "result": result.model_dump(mode="json")}


@router.post("/returns/{return_id}/compute")
def compute_return(return_id: str, db: Session = Depends(get_db)) -> dict:
    """Return the traceable profit→tax computation for the stored return."""
    rec = _get(db, return_id)
    ret = CorporateTaxReturn(**rec.return_json)
    return compute_ct(ret).model_dump(mode="json")


class StatusUpdate(BaseModel):
    status: str


@router.patch("/returns/{return_id}/status")
def set_status(return_id: str, body: StatusUpdate, db: Session = Depends(get_db)) -> dict:
    if body.status not in WORKFLOW_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {', '.join(WORKFLOW_STATES)}",
        )
    rec = _get(db, return_id)
    rec.status = body.status
    db.commit()
    return {"id": rec.id, "status": rec.status}


@router.delete("/returns/{return_id}")
def delete_return(return_id: str, db: Session = Depends(get_db)) -> dict:
    rec = _get(db, return_id)
    db.delete(rec)
    db.commit()
    return {"deleted": return_id}
