"""UAE VAT tax-code master + context-based resolver.

A single, centrally-defined master table (not hard-coded rules scattered across the
app) of the UAE VAT treatment codes — SR, ZR, EX, OOS, RC, GCC and the adjustment
codes — each carrying the fields an accounting VAT master needs (rate, flags, return
box, effective dates, regulatory reference). The resolver picks a code from the whole
transaction context and the **invoice date** (effective-date logic), and never infers a
treatment from the VAT percentage alone — an uncertain case resolves to REVIEW.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from . import constants as C
from .schemas import Invoice, InvoiceType, TransactionType, VatTreatment


@dataclass(frozen=True)
class TaxCodeDef:
    code: str
    name: str
    rate: Decimal | None                 # None = not applicable (exempt / out-of-scope / RC)
    treatment: VatTreatment | None
    tax_type: str                        # "sales" | "purchase" | "both"
    reverse_charge: bool = False
    zero_rated: bool = False
    exempt: bool = False
    out_of_scope: bool = False
    adjustment: bool = False
    vat_return_box: str = ""
    effective_from: date = date(2018, 1, 1)   # UAE VAT commenced 1 Jan 2018
    effective_to: date | None = None
    regulatory_ref: str = ""
    description: str = ""
    active: bool = True


_R5 = Decimal("0.05")

# ── The master table ─────────────────────────────────────────────────────────
TAX_CODES: list[TaxCodeDef] = [
    TaxCodeDef("SR", "Standard Rated", _R5, VatTreatment.STANDARD, "both",
               vat_return_box="Box 1 (sales) / Box 9 (purchases)",
               regulatory_ref="Federal Decree-Law No. 8 of 2017, Art. 3 (standard rate 5%)",
               description="Taxable local supplies at 5% that do not qualify for another treatment."),
    TaxCodeDef("ZR", "Zero Rated", Decimal("0"), VatTreatment.ZERO_RATED, "both",
               zero_rated=True, vat_return_box="Box 2 (sales)",
               regulatory_ref="Federal Decree-Law No. 8 of 2017, Art. 45 (zero-rated supplies)",
               description="Taxable supplies at 0% (qualifying exports, international transport, "
                           "qualifying new residential, etc.). Remains a taxable supply."),
    TaxCodeDef("EX", "Exempt", None, VatTreatment.EXEMPT, "both",
               exempt=True, vat_return_box="Box 3 approx (exempt supplies)",
               regulatory_ref="Federal Decree-Law No. 8 of 2017, Art. 46 (exempt supplies)",
               description="No VAT charged; input tax generally not recoverable. NOT the same as 0%."),
    TaxCodeDef("OOS", "Out of Scope", None, VatTreatment.OUT_OF_SCOPE, "both",
               out_of_scope=True, vat_return_box="Not reported",
               regulatory_ref="Outside the scope of UAE VAT (no UAE place of supply / non-taxable)",
               description="Genuinely outside UAE VAT scope. Not the same as exempt."),
    TaxCodeDef("RC", "Reverse Charge", None, VatTreatment.REVERSE_CHARGE, "purchase",
               reverse_charge=True, vat_return_box="Box 3 & Box 10 (self-account)",
               regulatory_ref="Federal Decree-Law No. 8 of 2017, Art. 48 (reverse charge)",
               description="Recipient self-accounts for VAT (imported goods/services & designated supplies)."),
    TaxCodeDef("GCC", "GCC / Intra-GCC", None, None, "both",
               vat_return_box="Depends on GCC framework implementation",
               regulatory_ref="GCC VAT Framework Agreement (implementing-state dependent)",
               description="Supply involving another GCC state — treatment depends on framework status."),
    TaxCodeDef("OADJ", "Output VAT Adjustment", None, None, "sales", adjustment=True,
               vat_return_box="Box 1 adjustment",
               regulatory_ref="Executive Regulation Art. 61 (output tax adjustments)",
               description="Adjustment/correction of previously reported output VAT."),
    TaxCodeDef("IADJ", "Input VAT Adjustment", None, None, "purchase", adjustment=True,
               vat_return_box="Box 9 adjustment",
               regulatory_ref="Executive Regulation Art. 55/56 (input tax adjustments)",
               description="Adjustment/correction of previously recovered input VAT."),
    TaxCodeDef("CN", "Credit Note Adjustment", None, None, "both", adjustment=True,
               vat_return_box="Reduces the linked supply's box",
               regulatory_ref="Executive Regulation Art. 60 (tax credit notes)",
               description="Credit note against an original tax invoice — links to the original transaction."),
    TaxCodeDef("DN", "Debit Note Adjustment", None, None, "both", adjustment=True,
               vat_return_box="Increases the linked supply's box",
               regulatory_ref="Executive Regulation Art. 60 (adjustment documents)",
               description="Debit note against an original tax invoice — links to the original transaction."),
]

_BY_CODE = {t.code: t for t in TAX_CODES}


def get_code(code: str) -> TaxCodeDef | None:
    return _BY_CODE.get(code)


def active_codes(as_of: date | None = None) -> list[TaxCodeDef]:
    """Master rows active as of a date (effective-date logic)."""
    d = as_of or date(2018, 1, 1)
    return [t for t in TAX_CODES if t.active and t.effective_from <= d and (t.effective_to is None or d <= t.effective_to)]


@dataclass
class TaxCodeResult:
    code: str
    name: str
    rate: Decimal | None
    certain: bool                 # False → the code needs human REVIEW
    reason: str
    taxable_amount: Decimal | None = None
    stated_vat: Decimal | None = None
    expected_vat: Decimal | None = None
    difference: Decimal | None = None


def _round(a: Decimal) -> Decimal:
    return a.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_iso(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d[:10])
    except ValueError:
        return None


def resolve_tax_code(inv: Invoice, txn: TransactionType | None = None,
                     master: dict | None = None) -> TaxCodeResult:
    """Resolve the VAT tax code, then apply the admin-configured master (rate/name)."""
    res = _resolve_core(inv, txn)
    if master:
        return _mk(res.code, res.certain, res.reason, inv, master)
    return res


def _resolve_core(inv: Invoice, txn: TransactionType | None = None) -> TaxCodeResult:
    """Pick a VAT tax code from the full context (parties, direction, document type,
    wording) — NOT from the rate alone. `certain=False` means REVIEW."""
    as_of = _parse_iso(inv.invoice_date)
    text_flags = {
        "exempt": inv.treatment == VatTreatment.EXEMPT,
        "rc": inv.has_reverse_charge_statement is True or inv.treatment == VatTreatment.REVERSE_CHARGE,
        "zero_stmt": inv.has_zero_rated_statement is True,
    }
    txn = txn or inv.transaction_type

    # Adjustment documents first.
    if inv.invoice_type == InvoiceType.CREDIT_NOTE:
        return _mk("CN", True, "Credit note — links to and reduces the original supply.", inv)
    if inv.invoice_type == InvoiceType.DEBIT_NOTE:
        return _mk("DN", True, "Debit note — links to and increases the original supply.", inv)

    # Reverse charge / import.
    if text_flags["rc"] or txn == TransactionType.IMPORT:
        return _mk("RC", False,
                   "Import / reverse-charge indication — recipient self-accounts; confirm and record in Box 3/10.",
                   inv)
    # GCC.
    if txn == TransactionType.GCC:
        return _mk("GCC", False, "Intra-GCC supply — treatment depends on GCC framework status; review.", inv)
    # Export (UAE -> overseas).
    if txn == TransactionType.EXPORT:
        return _mk("ZR", False,
                   "Cross-border export — zero-rating requires place-of-supply assessment and export "
                   "evidence; do not assume 0% without it.", inv)
    # Both overseas / no UAE nexus.
    if inv.supplier.is_uae is False and inv.recipient.is_uae is False:
        return _mk("OOS", False, "No UAE party detected — likely out of scope; confirm no UAE establishment.", inv)

    # Domestic (UAE -> UAE) or undetermined: use wording + rate as SIGNALS, not sole basis.
    if text_flags["exempt"]:
        return _mk("EX", False, "Exempt wording detected — confirm the supply qualifies as exempt (not 0%).", inv)

    rate = _detected_rate(inv)
    if rate == _R5:
        return _mk("SR", True, "Standard-rated 5% local supply.", inv)
    if rate == Decimal("0"):
        # 0% alone is NOT enough to conclude zero-rated (could be exempt/OOS/RC/error).
        return _mk("ZR", False,
                   "VAT shown as 0% — cannot be concluded from the rate alone; review whether zero-rated, "
                   "exempt, out-of-scope, or reverse-charge applies.", inv)
    # No usable rate → review.
    return _mk("SR", False, "VAT treatment could not be determined from the document — review required.", inv)


def _detected_rate(inv: Invoice) -> Decimal | None:
    if inv.line_items:
        rates = {li.vat_rate for li in inv.line_items if li.vat_rate is not None}
        if len(rates) == 1:
            return rates.pop()
    if inv.total_net and inv.total_vat is not None:
        if inv.total_vat == 0:
            return Decimal("0")
        try:
            r = (inv.total_vat / inv.total_net)
            if abs(r - _R5) <= Decimal("0.002"):
                return _R5
        except Exception:  # noqa: BLE001
            return None
    return None


def _mk(code: str, certain: bool, reason: str, inv: Invoice, master: dict | None = None) -> TaxCodeResult:
    d = _BY_CODE[code]
    # Prefer the admin-configured master row (rate/name) when supplied.
    row = (master or {}).get(code) or {}
    rate = row.get("rate", d.rate)
    name = row.get("name", d.name)
    taxable = inv.total_net
    stated = inv.total_vat
    expected = None
    diff = None
    if rate is not None and taxable is not None:
        expected = _round(taxable * rate)
        if stated is not None:
            diff = _round(stated - expected)
    return TaxCodeResult(
        code=code, name=name, rate=rate, certain=certain, reason=reason,
        taxable_amount=taxable, stated_vat=stated, expected_vat=expected, difference=diff,
    )


# ── configurable master (database) ───────────────────────────────────────────
def seed_tax_codes(db) -> int:
    """Seed the admin-editable VatTaxCode master from this built-in catalogue. Only
    inserts codes that don't already exist, so admin edits are never overwritten."""
    from ..models import VatTaxCode

    existing = {c for (c,) in db.query(VatTaxCode.code).all()} if hasattr(db, "query") else set()
    added = 0
    for t in TAX_CODES:
        if t.code in existing:
            continue
        db.add(VatTaxCode(
            code=t.code, name=t.name, rate=(str(t.rate) if t.rate is not None else None),
            treatment=(t.treatment.value if t.treatment else None), tax_type=t.tax_type,
            reverse_charge=t.reverse_charge, zero_rated=t.zero_rated, exempt=t.exempt,
            out_of_scope=t.out_of_scope, adjustment=t.adjustment, vat_return_box=t.vat_return_box,
            effective_from=t.effective_from.isoformat(),
            effective_to=(t.effective_to.isoformat() if t.effective_to else None),
            regulatory_ref=t.regulatory_ref, description=t.description, active=t.active,
        ))
        added += 1
    if added:
        db.commit()
    return added


def load_master(db) -> dict:
    """Load the configurable master into {code: {rate: Decimal|None, name: str}} for the
    resolver. Falls back silently to the built-in catalogue on any error."""
    out: dict = {}
    try:
        from ..models import VatTaxCode

        for row in db.query(VatTaxCode).all():
            rate = None
            if row.rate not in (None, "", "N/A"):
                try:
                    rate = Decimal(str(row.rate))
                except Exception:  # noqa: BLE001
                    rate = None
            out[row.code] = {"rate": rate, "name": row.name, "active": row.active}
    except Exception:  # noqa: BLE001
        return {}
    return out
