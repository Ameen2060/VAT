"""Generic, layout-agnostic extraction of invoice fields from raw (OCR'd) text.

This is deliberately NOT tuned to a single vendor's template. It combines:
- label→value parsing (tolerant of OCR that drops spaces, e.g. "CustomerTRN:123…"),
- positional/regex heuristics (TRNs, IBAN, email, phone, dates, currency),
- an amount-triple solver that finds (net, vat, gross) where net + vat = gross,
  which recovers totals and line-item amounts regardless of table layout.

Every populated field is accompanied by a confidence score (0..1). This is the
offline path (no API key). When an AI provider is configured, the AI extractor is
used instead for higher accuracy — but this remains the guaranteed fallback.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def _q(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

from ..vat.schemas import (
    Invoice,
    InvoiceType,
    LineItem,
    PartyDetails,
    PaymentInfo,
    TransactionType,
    VatTreatment,
)

# ── low-level patterns ───────────────────────────────────────────────────────
# Amounts: thousands-grouped (optional 1-2 decimals) OR a plain decimal (1-2 places).
# Covers "509,750", "25487.5", "1,302,500.00".
_AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2}")
_TRN_RE = re.compile(r"\b\d{15}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s()-]{7,}\d)")
# Dates in the common forms invoices use:
#   ISO (2026-07-24), D/M/Y (24/07/2026), "24 July 2026" (day-first), and
#   "July 24, 2026" (month-name-first). Month names are anchored so arbitrary
#   word+number text isn't mistaken for a date.
_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_DATE_RE = re.compile(
    r"(\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    rf"|\d{{1,2}}\s*{_MONTHS}\s*,?\s*\d{{2,4}}"
    rf"|{_MONTHS}\s+\d{{1,2}}\s*,?\s*\d{{2,4}}"
    r"|\d{1,2}\s*[A-Za-z]{3,9}\s*\d{4})",
    re.I,
)
# VAT rate in either order: "VAT 5%" or "5% VAT" or "5%VAT".
_VAT_RATE_RE = re.compile(
    r"VAT\s*\(?\s*(\d{1,2}(?:\.\d+)?)\s*%|(\d{1,2}(?:\.\d+)?)\s*%\s*VAT", re.I
)
# Invoice number without an explicit "Invoice No" label, e.g. "CMW/INV.76-26".
_INV_REF_RE = re.compile(r"\b((?:[A-Z]{2,6}[/-])?INV[.\s#:/-]*\d[\dA-Za-z/-]*)", re.I)
_SWIFT_RE = re.compile(r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")


def _detect_vat_rate(text: str) -> "Decimal | None":
    m = _VAT_RATE_RE.search(text)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        return Decimal(raw) / 100
    except (InvalidOperation, TypeError):
        return None


def _norm_label(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _to_decimal(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def _labels(text: str) -> dict[str, str]:
    """Map normalised label → value for every 'Label: value' line (first wins)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        key = _norm_label(label)
        value = value.strip()
        if key and value and key not in out:
            out[key] = value
    return out


def _first_label(labels: dict[str, str], *keys: str) -> str | None:
    for k in keys:
        if k in labels and labels[k]:
            return labels[k]
    return None


# ── amount-triple solver ─────────────────────────────────────────────────────
def _amounts(text: str) -> list[Decimal]:
    seen: list[Decimal] = []
    for m in _AMOUNT_RE.finditer(text):
        d = _to_decimal(m.group())
        if d is not None and d > 0:
            seen.append(d)
    return seen


def _find_triples(amounts: list[Decimal]) -> list[tuple[Decimal, Decimal, Decimal]]:
    """Return (net, vat, gross) triples where net + vat == gross, net being the
    larger addend (VAT is a fraction of net)."""
    uniq = sorted(set(amounts))
    present = set(uniq)
    triples: list[tuple[Decimal, Decimal, Decimal]] = []
    for i, a in enumerate(uniq):        # a <= b
        for b in uniq[i:]:
            c = a + b
            if b > 0 and c in present:
                triples.append((b, a, c))  # net=b (larger), vat=a (smaller), gross=c
    return triples


def _rate_consistent(net: Decimal, vat: Decimal, rate: Decimal) -> bool:
    """True if vat ≈ net × rate, tolerant only of rounding (2% of the expected VAT).
    Separates genuine invoice rows from coincidental sums (e.g. net1+net2) and stops
    a near-miss amount from being mistaken for a net/vat pair."""
    expected = net * rate
    tol = max(Decimal("0.10"), expected * Decimal("0.02"))
    return abs(vat - expected) <= tol


# ── document classification ──────────────────────────────────────────────────
def classify(text: str) -> InvoiceType:
    t = text.lower()
    compact = _norm_label(text)
    if "credit note" in t or "creditnote" in compact:
        return InvoiceType.CREDIT_NOTE
    if "debit note" in t or "debitnote" in compact:
        return InvoiceType.DEBIT_NOTE
    if "tax invoice" in t or "taxinvoice" in compact:
        return InvoiceType.TAX_INVOICE
    if "receipt" in t:
        return InvoiceType.RECEIPT
    if "invoice" in t:
        return InvoiceType.INVOICE
    return InvoiceType.UNKNOWN


_COMPANY_SUFFIX = re.compile(
    r"(L\.?L\.?C|LLC|FZ[- ]?LLC|FZE|FZCO|DMCC|W\.?L\.?L|LTD|LIMITED|"
    r"INC|PLC|EST\b|TRADING|CONTRACTING|GROUP|INDUSTRIES|CO\.)",
    re.I,
)


def _guess_supplier(text: str) -> tuple[str | None, str | None]:
    """The supplier is usually the letterhead: first company-looking line, followed
    by its address lines (until a TRN / 'tax invoice' / labelled field)."""
    lines = [ln.strip() for ln in text.splitlines()]
    name = None
    name_idx = -1
    for i, line in enumerate(lines[:8]):
        if len(line) > 4 and _COMPANY_SUFFIX.search(line):
            name = line
            name_idx = i
            break
    if name is None:
        return None, None

    addr_parts: list[str] = []
    for line in lines[name_idx + 1 : name_idx + 6]:
        low = line.lower()
        if not line or line == name:
            continue
        if "tax invoice" in low or _norm_label(line).startswith("trn") or ":" in line and _norm_label(
            line.split(":")[0]
        ) in {"trn", "customertrn", "taxinvoicenumber", "customerenglishlegalname"}:
            break
        if _COMPANY_SUFFIX.search(line) and line != name:
            break
        addr_parts.append(line)
    address = ", ".join(addr_parts) if addr_parts else None
    return name, address


_CUSTOMER_LABELS = (
    "customerenglishlegalname", "customername", "customer", "billto", "billedto",
    "billingname", "client", "clientname", "buyer", "soldto", "invoiceto", "deliverto",
    "ms", "mps", "messrs", "attn", "recipient",
)


def _clean_party_name(value: str) -> str:
    """Trim a name value that may have absorbed an adjacent column (e.g. an invoice
    ref merged onto the same OCR line). Cut at the end of a company suffix, or before
    an invoice-reference token."""
    value = value.strip()
    m = _COMPANY_SUFFIX.search(value)
    if m:
        return value[: m.end()].strip()
    ref = _INV_REF_RE.search(value)
    if ref and ref.start() > 2:
        return value[: ref.start()].strip()
    # otherwise keep it short and sane
    return " ".join(value.split()[:8])


# A "Bill To"-style indicator at the START of a line (incl. a bare "To,"/"To:").
_BILLTO_RE = re.compile(
    r"^\s*(bill\s*to|billed\s*to|sold\s*to|invoice\s*to|deliver\s*to|ship\s*to|to)\b[\s,:]*",
    re.I,
)


def _customer_name(text: str, labels: dict[str, str], supplier_name: str | None = None) -> str | None:
    """Detect the customer/recipient name using meaning, not fixed labels:
    1. an explicit customer label (same line),
    2. a "Bill To"/"To" block — value on the same line or the line below,
    3. semantic fallback — the first company entity near the top that is NOT the
       supplier (customers are almost always a distinct legal entity).
    Every candidate is cleaned (trimmed at the company suffix) and checked against the
    supplier so the two parties are never confused.
    """

    def _ok(name: str | None) -> bool:
        if not name or len(name) < 3:
            return False
        if supplier_name and (name == supplier_name or name.lower() in supplier_name.lower()):
            return False
        return True

    # 1. Explicit label on the same line.
    val = _first_label(labels, *_CUSTOMER_LABELS)
    if val and val.strip():
        name = _clean_party_name(val)
        if _ok(name):
            return name

    lines = [ln.strip() for ln in text.splitlines()]

    # 2. "Bill To"/"To" indicator → same-line remainder, else the next line.
    for i, line in enumerate(lines):
        key = _norm_label(line.split(":")[0]) if ":" in line else _norm_label(line)
        indicator = _BILLTO_RE.match(line) or key in _CUSTOMER_LABELS
        if not indicator:
            continue
        remainder = _BILLTO_RE.sub("", line).strip()
        candidates = [remainder]
        if i + 1 < len(lines):
            candidates.append(lines[i + 1])
        for cand in candidates:
            if not cand.strip():
                continue
            name = _clean_party_name(cand)
            if _ok(name) and _COMPANY_SUFFIX.search(name):
                return name
        # Accept a plausible next-line name even without a company suffix.
        if i + 1 < len(lines):
            nxt = _clean_party_name(lines[i + 1])
            if _ok(nxt) and ":" not in lines[i + 1][: len(nxt) + 1] and not nxt[0].isdigit():
                return nxt

    # 3. Semantic fallback: first company entity (near the top) that isn't the supplier.
    horizon = max(6, int(len(lines) * 0.6))
    for line in lines[:horizon]:
        if _COMPANY_SUFFIX.search(line):
            name = _clean_party_name(line)
            if _ok(name):
                return name
    return None


# ── main ─────────────────────────────────────────────────────────────────────
def parse_invoice(text: str) -> Invoice:
    inv = Invoice()
    conf: dict[str, float] = {}
    labels = _labels(text)
    compact = text.lower()

    def set_conf(field: str, score: float) -> None:
        conf[field] = score

    # Document type
    inv.invoice_type = classify(text)
    inv.has_tax_invoice_label = "tax invoice" in compact or "taxinvoice" in _norm_label(text)
    inv.has_reverse_charge_statement = "reverse charge" in compact

    # Invoice number — labelled first, else a reference pattern like "CMW/INV.76-26".
    num = _first_label(
        labels, "taxinvoicenumber", "invoicenumber", "invoiceno", "invoicenum", "invno",
        "billno", "documentno", "docno", "referenceno", "refno",
    )
    if num:
        inv.invoice_number = num.split()[0]
        set_conf("invoice_number", 0.9)
    else:
        m = _INV_REF_RE.search(text)
        if m:
            inv.invoice_number = m.group(1).strip()
            set_conf("invoice_number", 0.6)

    # Dates
    date = _first_label(labels, "date", "invoicedate", "dateofissue", "issuedate")
    if not date:
        m = _DATE_RE.search(text)
        date = m.group(1) if m else None
        if date:
            set_conf("invoice_date", 0.6)
    else:
        m = _DATE_RE.search(date)
        date = m.group(1) if m else date
        set_conf("invoice_date", 0.85)
    inv.invoice_date = date
    due = _first_label(labels, "duedate", "paymentdue", "dueon")
    if due:
        m = _DATE_RE.search(due)
        inv.due_date = m.group(1) if m else due
        set_conf("due_date", 0.85)

    # TRNs — labelled first, else positional (first = supplier, second = recipient).
    supplier = PartyDetails()
    recipient = PartyDetails()
    cust_trn = _first_label(
        labels, "customertrn", "recipienttrn", "buyertrn", "customervatno",
        "customervatnumber", "clienttrn",
    )
    all_trn = _TRN_RE.findall(text)
    if cust_trn:
        m = _TRN_RE.search(cust_trn)
        if m:
            recipient.trn = m.group()
            set_conf("recipient.trn", 0.9)
    # Supplier TRN: a labelled 'trn' that isn't the customer one, else first found.
    sup_trn_label = _first_label(
        labels, "trn", "suppliertrn", "vatnumber", "vatno", "vatregno", "vatregistrationno",
        "taxregistrationnumber", "trnno", "taxno",
    )
    if sup_trn_label:
        m = _TRN_RE.search(sup_trn_label)
        if m and m.group() != recipient.trn:
            supplier.trn = m.group()
            set_conf("supplier.trn", 0.9)
    if not supplier.trn:
        for t in all_trn:
            if t != recipient.trn:
                supplier.trn = t
                set_conf("supplier.trn", 0.6)
                break
    if not recipient.trn:
        for t in all_trn:
            if t != supplier.trn:
                recipient.trn = t
                set_conf("recipient.trn", 0.5)
                break

    # Names
    supplier.name, supplier.address = _guess_supplier(text)
    if supplier.name:
        set_conf("supplier.name", 0.6)
    if supplier.address:
        set_conf("supplier.address", 0.55)
    cust_name = _customer_name(text, labels, supplier.name)
    if cust_name:
        recipient.name = cust_name
        set_conf("recipient.name", 0.8)

    # Addresses / contacts
    addr = _first_label(labels, "registeredaddress", "customeraddress", "billingaddress", "address")
    if addr:
        recipient.address = addr
        set_conf("recipient.address", 0.7)
    email = _EMAIL_RE.search(text)
    if email:
        supplier.email = email.group()
        set_conf("supplier.email", 0.7)
    phone = _first_label(labels, "phone", "tel", "telephone", "mobile", "contact")
    if phone:
        pm = _PHONE_RE.search(phone)
        if pm:
            supplier.phone = pm.group().strip()
            set_conf("supplier.phone", 0.7)

    inv.supplier = supplier
    inv.recipient = recipient

    # Currency
    if re.search(r"\bAED\b|dirham", text, re.I):
        inv.currency = "AED"
    elif re.search(r"\bUSD\b|US\$|\$", text):
        inv.currency = "USD"
    elif re.search(r"\bEUR\b|€", text):
        inv.currency = "EUR"
    elif re.search(r"\bGBP\b|£", text):
        inv.currency = "GBP"
    elif re.search(r"\bSAR\b", text):
        inv.currency = "SAR"

    # VAT rate / treatment
    vat_rate = _detect_vat_rate(text)

    # ── Amounts: net / vat / gross via cross-checked relationships ─────────────
    # Two complementary signals, so it works whether or not the printed gross is
    # clean and regardless of how the columns are labelled:
    #   (a) printed triples where net + vat == gross, and
    #   (b) rate pairs where vat ≈ net × rate (gross computed) — robust to a
    #       truncated/oddly-rounded printed total (e.g. "535,237.").
    amounts = _amounts(text)
    candidates: list[tuple[Decimal, Decimal, Decimal]] = list(_find_triples(amounts))
    if vat_rate:
        amset = sorted(set(amounts))
        for net_c in amset:
            for vat_c in amset:
                if 0 < vat_c < net_c and _rate_consistent(net_c, vat_c, vat_rate):
                    candidates.append((net_c, vat_c, net_c + vat_c))

    if candidates:
        if vat_rate is None:
            big = max(candidates, key=lambda x: x[2])
            vat_rate = (big[1] / big[0]) if big[0] else Decimal("0")
        consistent = [c for c in candidates if vat_rate and _rate_consistent(c[0], c[1], vat_rate)]
        chosen = consistent or candidates

        # De-duplicate by (net, vat).
        seen: set[tuple[Decimal, Decimal]] = set()
        uniq: list[tuple[Decimal, Decimal, Decimal]] = []
        for c in sorted(chosen, key=lambda x: x[2]):
            if (c[0], c[1]) not in seen:
                seen.add((c[0], c[1]))
                uniq.append(c)

        net, vat, gross = max(uniq, key=lambda x: x[2])  # grand total = largest gross
        inv.total_net, inv.total_vat, inv.total_gross = net, vat, gross
        set_conf("total_net", 0.85)
        set_conf("total_vat", 0.85)
        set_conf("total_gross", 0.85)
        inv.treatment = VatTreatment.STANDARD if vat > 0 else VatTreatment.ZERO_RATED

        for a, b, c in uniq:
            if c == gross:
                continue  # skip the grand-total row
            inv.line_items.append(
                LineItem(
                    net_amount=a,
                    vat_amount=b,
                    line_total=c,
                    vat_rate=vat_rate,
                    treatment=VatTreatment.STANDARD if b > 0 else VatTreatment.ZERO_RATED,
                )
            )
        if inv.line_items:
            set_conf("line_items", 0.7)

    # VAT-inclusive vs VAT-exclusive single-total invoices: when no net/VAT pair was
    # found but a rate and a headline amount exist, derive the missing figures from
    # the stated inclusive/exclusive cue (net = gross ÷ (1+rate), or gross = net×(1+rate)).
    if inv.total_gross is None and vat_rate:
        inclusive = re.search(
            r"inclusive[^.\n]{0,20}vat|vat[^.\n]{0,20}inclusive|incl\.?\s*(?:of\s*)?vat", text, re.I
        )
        exclusive = re.search(
            r"exclusive[^.\n]{0,20}vat|vat[^.\n]{0,20}exclusive|plus\s*(?:\d+%?\s*)?vat"
            r"|before\s*vat|excl\.?\s*(?:of\s*)?vat",
            text,
            re.I,
        )
        amts = sorted(set(_amounts(text)), reverse=True)
        if amts and (inclusive or exclusive) and not (inclusive and exclusive):
            headline = amts[0]
            if inclusive:
                net = _q(headline / (Decimal(1) + vat_rate))
                inv.total_net, inv.total_vat, inv.total_gross = net, headline - net, headline
            else:  # exclusive
                vat = _q(headline * vat_rate)
                inv.total_net, inv.total_vat, inv.total_gross = headline, vat, headline + vat
            inv.treatment = VatTreatment.STANDARD
            for f in ("total_net", "total_vat", "total_gross"):
                set_conf(f, 0.6)  # derived, not directly printed

    # Payment info
    pay = PaymentInfo(
        bank_name=_first_label(labels, "bankname", "bank"),
        account_name=_first_label(labels, "accountname", "accnt", "accountholder"),
        account_number=_first_label(labels, "accountnumber", "accountno", "accno", "acnumber"),
        swift=_first_label(labels, "swiftcode", "swift", "bic"),
    )
    iban = _IBAN_RE.search(text)
    if iban:
        pay.iban = iban.group()
        set_conf("payment.iban", 0.9)
    if any([pay.bank_name, pay.account_name, pay.account_number, pay.swift, pay.iban]):
        inv.payment = pay

    inv.field_confidence = conf
    inv.notes = "Extracted by offline OCR + generic parser."
    return inv


def missing_fields(inv: Invoice) -> list[str]:
    """List important fields that were not confidently extracted."""
    checks = {
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "supplier.name": inv.supplier.name,
        "supplier.trn": inv.supplier.trn,
        "recipient.name": inv.recipient.name,
        "recipient.trn": inv.recipient.trn,
        "total_net": inv.total_net,
        "total_vat": inv.total_vat,
        "total_gross": inv.total_gross,
        "currency": inv.currency,
    }
    return [k for k, v in checks.items() if v in (None, "")]
