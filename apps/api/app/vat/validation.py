"""Validation & verification layer (pipeline step 4).

Runs AFTER extraction and BEFORE the deterministic compliance rules. Its job is to
separate two very different things:

* **Extraction gaps** — a field the OCR/parser could not confidently read. These
  become *verification items* (surfaced to the user with a confidence score) and
  must NEVER, on their own, make an invoice non-compliant.
* **Data-integrity checks** — cross-field relationships (net + VAT = gross,
  VAT ≈ net × rate, TRN format) computed on the values that WERE extracted. These
  feed the transparency view; genuine violations are raised as compliance findings
  by the rule engine.

Nothing here decides Pass/Fail. It decides what is *known*, what is *uncertain*, and
what still needs a human — so the compliance verdict is based on real invoice data.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from . import constants as C
from .schemas import Invoice, ValidationCheck, VerificationItem

_LOW_CONF = 0.5  # below this, a populated field is still flagged for verification

# Important fields, their human label, and whether a value is contextually required.
_FIELDS: list[tuple[str, str]] = [
    ("invoice_number", "Invoice number"),
    ("invoice_date", "Invoice date"),
    ("supplier.name", "Supplier / vendor name"),
    ("supplier.trn", "Supplier TRN / VAT number"),
    ("recipient.name", "Customer / buyer name"),
    ("recipient.trn", "Customer TRN / VAT number"),
    ("total_net", "Net / subtotal amount"),
    ("total_vat", "VAT / tax amount"),
    ("total_gross", "Gross / total amount"),
    ("currency", "Currency"),
]


def _get(inv: Invoice, path: str):
    if "." in path:
        head, tail = path.split(".", 1)
        obj = getattr(inv, head, None)
        return getattr(obj, tail, None) if obj is not None else None
    return getattr(inv, path, None)


def _valid_trn(trn) -> bool:
    if trn is None or str(trn).strip() == "":
        return False
    digits = "".join(ch for ch in str(trn) if ch.isdigit())
    return len(digits) == C.TRN_LENGTH and digits == str(trn).strip()


def _to_decimal(v) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _evidence(field: str, raw: str) -> bool:
    """Heuristic: does the raw document text suggest this value is present somewhere,
    even though extraction missed it? Used to tell 'OCR missed it' apart from
    'genuinely absent'."""
    t = raw.lower()
    compact = re.sub(r"[^a-z0-9]", "", t)
    if field in ("supplier.trn", "recipient.trn"):
        return bool(re.search(r"\d{15}", raw)) or "trn" in compact or "vat" in t or "taxreg" in compact
    if field == "invoice_number":
        return "invoice" in t or "inv" in compact or "billno" in compact or "refno" in compact
    if field == "invoice_date":
        return "date" in t or bool(re.search(r"\d{1,2}[/-]\d{1,2}", raw))
    if field in ("total_net", "total_vat", "total_gross"):
        return bool(re.search(r"\d[\d,]*\.?\d*", raw)) and any(
            k in compact for k in ("total", "net", "vat", "tax", "subtotal", "amount", "gross", "due")
        )
    if field in ("supplier.name", "recipient.name"):
        return bool(
            re.search(r"l\.?l\.?c|fze|dmcc|ltd|limited|trading|contracting|est\b|company", t)
        ) or any(k in compact for k in ("billto", "customer", "supplier", "vendor", "client", "ms"))
    if field == "currency":
        return bool(re.search(r"aed|usd|eur|gbp|sar|dirham|\$|€|£", t))
    return False


def build_verification_items(inv: Invoice, raw_text: str) -> list[VerificationItem]:
    conf = inv.field_confidence or {}
    items: list[VerificationItem] = []
    for field, label in _FIELDS:
        # A UAE TRN is NOT required for a party established outside the UAE — never flag
        # its absence as a gap (it is "Not applicable", handled by the party assessment).
        if field == "supplier.trn" and inv.supplier.is_uae is False:
            continue
        if field == "recipient.trn" and inv.recipient.is_uae is False:
            continue
        value = _get(inv, field)
        has_score = field in conf
        score = float(conf.get(field, 0.0) or 0.0)
        present = value is not None and str(value).strip() != ""

        if present:
            # A present value is only flagged when it carries an explicit LOW score.
            # Present-with-no-tracked-score counts as detected (e.g. currency).
            if has_score and score < _LOW_CONF:
                items.append(
                    VerificationItem(
                        field=field, label=label, confidence=score, status="low_confidence",
                        likely_present=True,
                        reason=f"Detected as “{value}” but with low confidence.",
                        recommendation="Confirm or correct this value before finalising.",
                    )
                )
            continue
        # Not present in the extracted data.
        evidence = _evidence(field, raw_text)
        items.append(
            VerificationItem(
                field=field, label=label, confidence=0.0, status="not_detected",
                likely_present=evidence,
                reason=(
                    "Not auto-extracted, but the document appears to contain related content — "
                    "likely an OCR/layout miss."
                    if evidence
                    else "Not found in the extracted text; may be genuinely absent."
                ),
                recommendation="Review the original document and enter the value if present.",
            )
        )
    return items


def build_validations(inv: Invoice) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    tol = Decimal(str(C.CALC_TOLERANCE_AED))

    net, vat, gross = inv.total_net, inv.total_vat, inv.total_gross
    if net is not None and vat is not None and gross is not None:
        ok = abs((net + vat) - gross) <= tol
        checks.append(ValidationCheck(
            name="Net + VAT = Gross", passed=ok,
            detail=f"{net} + {vat} = {net + vat} vs stated gross {gross}"
            + ("" if ok else " — mismatch"),
        ))

    if net is not None and vat is not None and net > 0:
        from .schemas import VatTreatment

        implied = (vat / net) if net else Decimal(0)
        near5 = abs(implied - Decimal(str(C.STANDARD_RATE))) <= Decimal("0.005")
        # 0% is a valid rate: zero-rated / exempt / out-of-scope supplies carry no VAT.
        zero_rated = vat == 0 or implied <= Decimal("0.005") or inv.treatment in (
            VatTreatment.ZERO_RATED, VatTreatment.EXEMPT, VatTreatment.OUT_OF_SCOPE,
        )
        detail = (
            "0% — zero-rated / no VAT (accepted)" if zero_rated and not near5
            else f"Implied VAT rate ≈ {round(float(implied) * 100, 2)}% of net"
        )
        checks.append(ValidationCheck(
            name="VAT rate consistency", passed=near5 or zero_rated, detail=detail,
        ))

    if inv.supplier and inv.supplier.trn:
        checks.append(ValidationCheck(
            name="Supplier TRN format (15 digits)", passed=_valid_trn(inv.supplier.trn),
            detail=str(inv.supplier.trn),
        ))
    if inv.recipient and inv.recipient.trn:
        checks.append(ValidationCheck(
            name="Customer TRN format (15 digits)", passed=_valid_trn(inv.recipient.trn),
            detail=str(inv.recipient.trn),
        ))

    checks.append(ValidationCheck(
        name="Currency identified", passed=bool(inv.currency),
        detail=inv.currency or "not identified",
    ))
    return checks


def validate_invoice(inv: Invoice, raw_text: str = "") -> tuple[list[VerificationItem], list[ValidationCheck]]:
    return build_verification_items(inv, raw_text), build_validations(inv)
