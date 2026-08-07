"""VAT201 Return API: generate from a transactions file, view, drill-down, export."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Vat201ReturnRecord, Vat201TxnRecord
from ..vat201.refund import prepare_refund311
from ..vat201.service import generate_return

router = APIRouter(prefix="/api/vat201", tags=["vat201"])


class ReturnSummary(BaseModel):
    id: str
    company_name: str | None
    company_trn: str | None
    period_type: str
    period_label: str
    net_vat_due: str
    is_refund: bool
    status: str
    created_at: str | None


def _summary(r: Vat201ReturnRecord) -> ReturnSummary:
    return ReturnSummary(
        id=r.id, company_name=r.company_name, company_trn=r.company_trn,
        period_type=r.period_type, period_label=r.period_label,
        net_vat_due=r.net_vat_due, is_refund=r.is_refund, status=r.status,
        created_at=r.created_at.isoformat() if r.created_at else None,
    )


@router.post("/generate", response_model=dict)
async def generate(
    file: UploadFile = File(...),
    company_name: str | None = Form(None),
    company_trn: str | None = Form(None),
    period_type: str = Form("quarter"),
    year: int = Form(...),
    index: int = Form(...),
    filter_by_date: bool = Form(True),
    default_emirate: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    if period_type not in ("month", "quarter"):
        raise HTTPException(status_code=400, detail="period_type must be 'month' or 'quarter'")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if not (file.filename or "").lower().endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=415, detail="Upload a .csv or .xlsx transactions file")
    rec = generate_return(
        db, filename=file.filename or "transactions.csv", data=data,
        company_name=company_name, company_trn=company_trn,
        period_type=period_type, year=year, index=index,
        filter_by_date=filter_by_date, default_emirate=default_emirate,
    )
    return {"id": rec.id, "return": rec.return_json}


@router.get("/returns", response_model=list[ReturnSummary])
def list_returns(db: Session = Depends(get_db)) -> list[ReturnSummary]:
    rows = db.execute(select(Vat201ReturnRecord).order_by(Vat201ReturnRecord.created_at.desc())).scalars()
    return [_summary(r) for r in rows]


@router.get("/returns/{return_id}")
def get_return(return_id: str, db: Session = Depends(get_db)) -> dict:
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    return {"id": r.id, "status": r.status, "return": r.return_json}


@router.get("/returns/{return_id}/transactions")
def drill_down(return_id: str, box: str | None = Query(None), db: Session = Depends(get_db)) -> list[dict]:
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    rows = db.execute(
        select(Vat201TxnRecord).where(Vat201TxnRecord.return_id == return_id)
    ).scalars()
    out = []
    for t in rows:
        if box and box not in (t.boxes or []):
            continue
        out.append({
            "row_index": t.row_index, "date": t.date, "doc_type": t.doc_type,
            "direction": t.direction, "party": t.party, "trn": t.trn,
            "invoice_number": t.invoice_number, "emirate": t.emirate,
            "treatment": t.treatment, "taxable_amount": t.taxable_amount,
            "vat_amount": t.vat_amount, "boxes": t.boxes,
        })
    return out


class Refund311Request(BaseModel):
    amount_requested: float | None = None
    late_registration_penalty: float = 0
    legal_name: str | None = None
    authorized_signatory: str | None = None
    declaration_date: str | None = None


@router.post("/returns/{return_id}/refund311")
def prepare_refund(return_id: str, body: Refund311Request, db: Session = Depends(get_db)) -> dict:
    """Prepare the VAT311 refund application from this return (must be a refund)."""
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    try:
        app = prepare_refund311(
            is_refund=r.is_refund, net_vat_due=r.net_vat_due, trn=r.company_trn,
            company_name=r.company_name, period_label=r.period_label,
            amount_requested=body.amount_requested,
            late_registration_penalty=body.late_registration_penalty,
            legal_name=body.legal_name, authorized_signatory=body.authorized_signatory,
            declaration_date=body.declaration_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    r.refund311_json = app.model_dump()
    db.commit()
    return app.model_dump()


@router.get("/returns/{return_id}/refund311")
def get_refund(return_id: str, db: Session = Depends(get_db)) -> dict:
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    if not r.refund311_json:
        raise HTTPException(status_code=404, detail="No VAT311 prepared for this return")
    return r.refund311_json


@router.get("/returns/{return_id}/refund311/export")
def export_refund(return_id: str, db: Session = Depends(get_db)):
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    if not r.refund311_json:
        raise HTTPException(status_code=404, detail="Prepare the VAT311 application first")
    from ..services.report import build_vat311_pdf

    pdf = build_vat311_pdf(r.refund311_json)
    if pdf is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable")
    fname = f"VAT311-Refund-{r.period_label or r.id}"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
    )


@router.get("/returns/{return_id}/faf")
def export_faf(return_id: str, db: Session = Depends(get_db)):
    """Generate the FTA Audit File (FAF) workbook for this return.

    Produces the official FTA VAT-audit Excel format: a Required-information sheet,
    a VAT Return summary, and one transaction-listing sheet per VAT201 box, all
    populated from this return's stored transactions.
    """
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    from ..faf import build_faf_workbook

    txns = list(
        db.execute(
            select(Vat201TxnRecord)
            .where(Vat201TxnRecord.return_id == return_id)
            .order_by(Vat201TxnRecord.row_index)
        ).scalars()
    )
    try:
        content = build_faf_workbook(r.return_json or {}, txns)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail="FAF template not available") from e
    fname = f"FAF-{r.period_label or r.id}"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'},
    )


@router.delete("/returns/{return_id}")
def delete_return(return_id: str, db: Session = Depends(get_db)) -> dict:
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    db.delete(r)
    db.commit()
    return {"deleted": return_id}


# ── Exports ──────────────────────────────────────────────────────────────────
def _boxes_rows(ret: dict) -> list[list]:
    rows = [["Box", "Description", "Amount (AED)", "VAT (AED)"]]
    for b in ret.get("boxes", []):
        rows.append([b["box"], b["label"], b["amount"], b["vat"]])
    return rows


@router.get("/returns/{return_id}/export")
def export_return(return_id: str, format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"), db: Session = Depends(get_db)):
    r = db.get(Vat201ReturnRecord, return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Return not found")
    ret = r.return_json or {}
    fname = f"VAT201-{r.period_label or r.id}"

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["UAE VAT Return (VAT201)"])
        w.writerow(["Company", ret.get("company_name")])
        w.writerow(["TRN", ret.get("company_trn")])
        w.writerow(["Period", ret.get("period_label"), "Due", ret.get("due_date")])
        w.writerow([])
        for row in _boxes_rows(ret):
            w.writerow(row)
        return Response(
            content=buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'},
        )

    if format == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "VAT201"
        ws.append(["UAE VAT Return (VAT201)"])
        ws.append(["Company", ret.get("company_name"), "TRN", ret.get("company_trn")])
        ws.append(["Period", ret.get("period_label"), "Due", ret.get("due_date")])
        ws.append([])
        for row in _boxes_rows(ret):
            ws.append(row)
        tx = wb.create_sheet("Transactions")
        tx.append(["Row", "Date", "Doc type", "Direction", "Party", "TRN", "Invoice",
                   "Emirate", "Treatment", "Taxable", "VAT", "Boxes"])
        for t in db.execute(
            select(Vat201TxnRecord).where(Vat201TxnRecord.return_id == return_id)
        ).scalars():
            tx.append([t.row_index, t.date, t.doc_type, t.direction, t.party, t.trn,
                       t.invoice_number, t.emirate, t.treatment, t.taxable_amount,
                       t.vat_amount, ",".join(t.boxes or [])])
        out = io.BytesIO()
        wb.save(out)
        return Response(
            content=out.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'},
        )

    # PDF
    from ..services.report import build_vat201_pdf

    pdf = build_vat201_pdf(ret)
    if pdf is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable (install reportlab)")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
    )
