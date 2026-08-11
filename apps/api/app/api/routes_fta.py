"""FTA VAT Regulatory Update Monitoring & Update API.

Change-log CRUD + review workflow, official-source monitoring, and the effective-dated
VAT rule registry (source traceability). Mutations that affect the live rule set or move
an update toward implementation are admin-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import require_admin
from ..core.database import get_db
from ..fta import monitor, service
from ..fta.seed import seed_fta
from ..models import FtaSource, FtaUpdate, User, VatRuleVersion

router = APIRouter(prefix="/api/fta", tags=["fta"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class UpdateIn(BaseModel):
    title: str
    update_type: str = "public_clarification"
    classification: str = "informational"
    critical: bool = False
    publication_date: str | None = None
    effective_date: str | None = None
    previous_rule: str | None = None
    new_rule: str | None = None
    affected_module: str | None = None
    affected_treatment: str | None = None
    source_ref: str | None = None
    notes: str | None = None


class UpdateOut(UpdateIn):
    id: str
    status: str
    approved_by: str | None = None
    implemented_at: str | None = None
    validation: dict | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TransitionIn(BaseModel):
    status: str  # under_review | approved | implemented | rejected | new


class SourceOut(BaseModel):
    id: str
    name: str
    url: str
    authority: str
    category: str
    is_active: bool
    last_status: str
    last_checked_at: str | None
    note: str | None


class RuleOut(BaseModel):
    id: str
    rule_key: str
    title: str
    category: str
    value: str | None
    effective_from: str
    effective_to: str | None
    source_ref: str
    status: str


def _update_out(u: FtaUpdate) -> UpdateOut:
    return UpdateOut(
        id=u.id, title=u.title, update_type=u.update_type, classification=u.classification,
        status=u.status, critical=u.critical, publication_date=u.publication_date,
        effective_date=u.effective_date, previous_rule=u.previous_rule, new_rule=u.new_rule,
        affected_module=u.affected_module, affected_treatment=u.affected_treatment,
        source_ref=u.source_ref, notes=u.notes, approved_by=u.approved_by,
        implemented_at=u.implemented_at.isoformat() if u.implemented_at else None,
        validation=u.validation_json, created_by=u.created_by,
        created_at=u.created_at.isoformat() if u.created_at else None,
        updated_at=u.updated_at.isoformat() if u.updated_at else None,
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────
@router.get("/dashboard")
def fta_dashboard(db: Session = Depends(get_db)) -> dict:
    return service.dashboard(db)


@router.post("/seed")
def seed(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    return seed_fta(db)


# ── Change log (updates) ──────────────────────────────────────────────────────
@router.get("/updates", response_model=list[UpdateOut])
def list_updates(
    status: str | None = Query(None),
    update_type: str | None = Query(None),
    critical: bool | None = Query(None),
    db: Session = Depends(get_db),
) -> list[UpdateOut]:
    stmt = select(FtaUpdate).order_by(FtaUpdate.created_at.desc())
    if status:
        stmt = stmt.where(FtaUpdate.status == status)
    if update_type:
        stmt = stmt.where(FtaUpdate.update_type == update_type)
    if critical is not None:
        stmt = stmt.where(FtaUpdate.critical.is_(critical))
    return [_update_out(u) for u in db.execute(stmt).scalars()]


@router.post("/updates", response_model=UpdateOut)
def create_update(
    body: UpdateIn, user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UpdateOut:
    u = FtaUpdate(**body.model_dump(), status="new", created_by=getattr(user, "email", None))
    db.add(u)
    db.commit()
    db.refresh(u)
    return _update_out(u)


@router.get("/updates/{update_id}", response_model=UpdateOut)
def get_update(update_id: str, db: Session = Depends(get_db)) -> UpdateOut:
    u = db.get(FtaUpdate, update_id)
    if not u:
        raise HTTPException(status_code=404, detail="Update not found")
    return _update_out(u)


@router.patch("/updates/{update_id}", response_model=UpdateOut)
def edit_update(
    update_id: str, body: UpdateIn, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UpdateOut:
    u = db.get(FtaUpdate, update_id)
    if not u:
        raise HTTPException(status_code=404, detail="Update not found")
    for k, v in body.model_dump().items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return _update_out(u)


@router.post("/updates/{update_id}/transition", response_model=UpdateOut)
def transition_update(
    update_id: str, body: TransitionIn, user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UpdateOut:
    u = db.get(FtaUpdate, update_id)
    if not u:
        raise HTTPException(status_code=404, detail="Update not found")
    try:
        service.transition(db, u, body.status, getattr(user, "email", None))
    except service.TransitionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _update_out(u)


@router.delete("/updates/{update_id}")
def delete_update(
    update_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    u = db.get(FtaUpdate, update_id)
    if not u:
        raise HTTPException(status_code=404, detail="Update not found")
    db.delete(u)
    db.commit()
    return {"deleted": update_id}


# ── Monitored sources ─────────────────────────────────────────────────────────
@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[SourceOut]:
    rows = db.execute(select(FtaSource).order_by(FtaSource.authority, FtaSource.name)).scalars()
    return [
        SourceOut(
            id=s.id, name=s.name, url=s.url, authority=s.authority, category=s.category,
            is_active=s.is_active, last_status=s.last_status,
            last_checked_at=s.last_checked_at.isoformat() if s.last_checked_at else None,
            note=s.note,
        )
        for s in rows
    ]


@router.post("/sources/check")
def check_sources(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Fetch every active source and flag content changes as NEW signals for review."""
    return monitor.check_all_sources(db)


@router.post("/sources/check/{source_id}")
def check_one_source(
    source_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    s = db.get(FtaSource, source_id)
    if not s:
        raise HTTPException(status_code=404, detail="Source not found")
    return monitor.check_source(db, s)


# ── Effective-dated rule registry (source traceability) ───────────────────────
@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db)) -> list[RuleOut]:
    rows = db.execute(
        select(VatRuleVersion).order_by(VatRuleVersion.rule_key, VatRuleVersion.effective_from.desc())
    ).scalars()
    return [
        RuleOut(
            id=r.id, rule_key=r.rule_key, title=r.title, category=r.category, value=r.value,
            effective_from=r.effective_from, effective_to=r.effective_to,
            source_ref=r.source_ref, status=r.status,
        )
        for r in rows
    ]


@router.get("/rules/as-of", response_model=RuleOut)
def rule_as_of(rule_key: str, on: str | None = Query(None), db: Session = Depends(get_db)) -> RuleOut:
    """The rule version that applied on a given date (defaults to today)."""
    r = service.rule_as_of(db, rule_key, on)
    if not r:
        raise HTTPException(status_code=404, detail="No rule version in force for that key/date")
    return RuleOut(
        id=r.id, rule_key=r.rule_key, title=r.title, category=r.category, value=r.value,
        effective_from=r.effective_from, effective_to=r.effective_to,
        source_ref=r.source_ref, status=r.status,
    )
