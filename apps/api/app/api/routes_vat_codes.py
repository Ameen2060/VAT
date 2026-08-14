"""Configurable VAT tax-code master — admin-managed CRUD.

The master (SR/ZR/EX/OOS/RC/GCC + adjustments) is seeded on boot and editable here so
VAT treatments/rates/return-boxes are maintained centrally, without code changes. The
Document Analysis resolver reads rate/name from this table (app.vat.tax_codes.load_master).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user, require_admin
from ..core.database import get_db
from ..models import User, VatTaxCode

router = APIRouter(prefix="/api/vat-codes", tags=["vat-codes"])


class VatCodeOut(BaseModel):
    code: str
    name: str
    rate: str | None = None
    treatment: str | None = None
    tax_type: str
    reverse_charge: bool
    zero_rated: bool
    exempt: bool
    out_of_scope: bool
    adjustment: bool
    vat_return_box: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    regulatory_ref: str | None = None
    description: str | None = None
    active: bool
    updated_by: str | None = None


class VatCodeUpdate(BaseModel):
    name: str | None = None
    rate: str | None = None
    tax_type: str | None = None
    vat_return_box: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    regulatory_ref: str | None = None
    description: str | None = None
    active: bool | None = None
    reverse_charge: bool | None = None
    zero_rated: bool | None = None
    exempt: bool | None = None
    out_of_scope: bool | None = None
    adjustment: bool | None = None


class VatCodeCreate(VatCodeUpdate):
    code: str
    name: str


def _out(r: VatTaxCode) -> VatCodeOut:
    return VatCodeOut(
        code=r.code, name=r.name, rate=r.rate, treatment=r.treatment, tax_type=r.tax_type,
        reverse_charge=r.reverse_charge, zero_rated=r.zero_rated, exempt=r.exempt,
        out_of_scope=r.out_of_scope, adjustment=r.adjustment, vat_return_box=r.vat_return_box,
        effective_from=r.effective_from, effective_to=r.effective_to,
        regulatory_ref=r.regulatory_ref, description=r.description, active=r.active,
        updated_by=r.updated_by,
    )


@router.get("", response_model=list[VatCodeOut])
def list_codes(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[VatCodeOut]:
    rows = db.execute(select(VatTaxCode).order_by(VatTaxCode.code)).scalars().all()
    return [_out(r) for r in rows]


@router.put("/{code}", response_model=VatCodeOut)
def update_code(code: str, body: VatCodeUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)) -> VatCodeOut:
    row = db.get(VatTaxCode, code)
    if not row:
        raise HTTPException(status_code=404, detail="Tax code not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = getattr(admin, "email", None)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("", response_model=VatCodeOut, status_code=201)
def create_code(body: VatCodeCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)) -> VatCodeOut:
    code = body.code.strip().upper()
    if db.get(VatTaxCode, code):
        raise HTTPException(status_code=409, detail="Tax code already exists")
    data = body.model_dump(exclude_unset=True)
    data.pop("code", None)
    row = VatTaxCode(code=code, updated_by=getattr(admin, "email", None), **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)
