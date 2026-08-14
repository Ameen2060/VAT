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
    r"INC|PLC|EST\b|TRADING|CONTRACTING|GROUP|INDUSTRIES|CO\.|"
    # International suffixes (multi-char only, to avoid matching inside words) so
    # overseas suppliers/customers are recognised too.
    r"GMBH|S\.?A\.?R\.?L|PVT|PTE|CORP|CORPORATION|ENTERPRISES|SDN\s?BHD|LLP)",
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

    # 1b. Tolerant scan: find a customer label anywhere on a line (handles bilingual /
    #     RTL layouts the colon-based label map misses) and take the value remainder.
    _CUST_KEYS = ("clientname", "customername", "customer", "client", "billto",
                  "soldto", "invoiceto", "buyer")
    _CUST_NEG = ("customerno", "customertrn", "customeraccount", "customervat", "customercode")
    for line in text.splitlines():
        norm = _norm_label(line)
        if not norm or any(neg in norm for neg in _CUST_NEG):
            continue
        if not any(k in norm for k in _CUST_KEYS):
            continue
        cleaned = _ARABIC_RE.sub(" ", line)
        cleaned = re.sub(
            r"(?i)\b(client\s*name|customer\s*name|client|customer|bill\s*to|sold\s*to|"
            r"invoice\s*to|buyer|name|messrs|m/?s)\b[:.\-]*",
            " ",
            cleaned,
        ).strip(" :.-/")
        if len(cleaned) >= 3:
            name = _clean_party_name(cleaned)
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


def _address_near_name(text: str, name: str, supplier_address: str | None = None) -> str | None:
    """Return the address block sitting just after the customer's name line, so the
    recipient address is never confused with the supplier's letterhead address."""
    lines = [ln.strip() for ln in text.splitlines()]
    key = _norm_label(name)[:14]
    idx = next((i for i, ln in enumerate(lines) if key and key in _norm_label(ln)), -1)
    if idx < 0:
        return None
    for j in range(idx, min(idx + 5, len(lines))):
        ln = lines[j]
        head = _norm_label(ln.split(":")[0]) if ":" in ln else ""
        if head in ("address", "add", "customeraddress", "billingaddress", "clientaddress"):
            val = ln.split(":", 1)[1].strip()
            parts = [val] if val else []
            for k in range(j + 1, min(j + 3, len(lines))):
                nxt = lines[k]
                if not nxt or ":" in nxt or _COMPANY_SUFFIX.search(nxt):
                    break
                parts.append(nxt)
            addr = ", ".join(p for p in parts if p)
            if addr and addr != (supplier_address or ""):
                return addr
    return None


# ── source-evidence locator (Level-4 traceability) ────────────────────────────
def _num_candidates(value) -> list[str]:
    """Textual forms an amount might appear as in the document (plain, grouped, no
    trailing zeros)."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return [str(value)]
    s = format(d, "f")
    out = {s}
    intpart, _, frac = s.partition(".")
    grouped = f"{int(intpart):,}" if intpart.lstrip("-").isdigit() else intpart
    out.add(grouped)
    if frac:
        out.add(f"{grouped}.{frac}")
        if frac == "00":
            out.add(intpart)
            out.add(grouped)
    return [c for c in out if c]


def _locate(text: str, value, numeric: bool = False) -> dict | None:
    """Find the first line/character span where `value` appears in the document text."""
    if value in (None, ""):
        return None
    candidates = _num_candidates(value) if numeric else [str(value)]
    # Longest first so we anchor on the most specific match.
    candidates = sorted({c for c in candidates if c}, key=len, reverse=True)
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()  # snippet offsets are relative to the trimmed line
        for c in candidates:
            idx = line.find(c)
            if idx >= 0:
                return {"snippet": line, "line_no": i, "start": idx, "end": idx + len(c)}
    return None


def _build_evidence(text: str, inv: "Invoice") -> dict[str, dict]:
    """Locate each populated field's value in the document text — the Level-4 provenance."""
    targets: list[tuple[str, object, bool]] = [
        ("invoice_number", inv.invoice_number, False),
        ("invoice_date", inv.invoice_date, False),
        ("due_date", inv.due_date, False),
        ("supplier.name", inv.supplier.name, False),
        ("supplier.trn", inv.supplier.trn, False),
        ("supplier.email", inv.supplier.email, False),
        ("supplier.phone", inv.supplier.phone, False),
        ("recipient.name", inv.recipient.name, False),
        ("recipient.trn", inv.recipient.trn, False),
        ("recipient.address", inv.recipient.address, False),
        ("total_net", inv.total_net, True),
        ("total_vat", inv.total_vat, True),
        ("total_gross", inv.total_gross, True),
        ("payment.iban", inv.payment.iban if inv.payment else None, False),
    ]
    ev: dict[str, dict] = {}
    for field, value, numeric in targets:
        loc = _locate(text, value, numeric=numeric)
        if loc:
            ev[field] = loc
    return ev


# ── robust invoice-number & date extraction ──────────────────────────────────
# These tolerate bilingual (Arabic/English) and colon-less layouts: they scan every
# line for a label keyword and pull the value token from anywhere on the line, so an
# RTL-reordered "value : label" line is handled the same as "label: value".
_ARABIC_RE = re.compile(r"[؀-ۿ]+")

# Invoice-number labels, most-specific first, with a confidence score. NOTE: a bare
# "invoice" is intentionally excluded — it also matches "Invoice Amount/Value/Total",
# which must never be read as the invoice number.
_INV_NUM_LABELS: list[tuple[str, int]] = [
    ("taxinvoiceno", 10), ("taxinvoicenumber", 10),
    ("invoiceno", 9), ("invoicenumber", 9), ("invoicenum", 9), ("invoicenbr", 9),
    ("invno", 8), ("invoiceref", 8), ("invoicereference", 8),
    ("billno", 8), ("billnumber", 8),
    ("documentno", 5), ("documentnumber", 5), ("docno", 5),
    ("referenceno", 4), ("referencenumber", 4), ("refno", 4),
    # Bare "invoice" (covers "Invoice #") kept last & low: the monetary negative labels
    # and the bare-number guard stop "Invoice Amount 437,179.05" being read as a number.
    ("invoice", 5),
]
# Labels whose number must NEVER populate the invoice-number field — includes monetary
# labels ("invoice amount/value/total") so a total is never mistaken for a number.
_NEG_NUM_LABELS = (
    "purchaseorder", "pono", "ponumber", "lpono", "lpo", "contractno", "contractnumber",
    "deliveryno", "deliverynote", "quoteno", "quotationno", "customerno", "customeraccount",
    "accountno", "accountnumber", "crno", "crnumber", "trn", "vatno", "vatnumber",
    "taxregistration", "hscode", "serialno",
    "invoiceamount", "invoicevalue", "invoicetotal", "totalamount", "amountdue",
    "grandtotal", "totalinvoice", "netamount", "vatamount", "totaldue", "balancedue",
)


def _is_trn_token(tok: str) -> bool:
    digits = "".join(ch for ch in tok if ch.isdigit())
    return len(digits) == 15 and digits == tok


def _looks_like_date_token(tok: str) -> bool:
    if _DATE_RE.fullmatch(tok):
        return True
    # d/m/y or d-m-y or d.m.y all-numeric
    return bool(re.fullmatch(r"\d{1,4}[/.\-]\d{1,2}[/.\-]\d{2,4}", tok))


def _num_tokens(line: str) -> list[str]:
    """Invoice-number-shaped tokens on a line: alphanumeric with -/._# separators,
    containing at least one digit, excluding TRNs and dates."""
    cleaned = _ARABIC_RE.sub(" ", line)
    out: list[str] = []
    for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9/._#-]{1,28}[A-Za-z0-9]", cleaned):
        tok = m.group().strip("#.:-/ ")
        if not tok or not any(ch.isdigit() for ch in tok):
            continue
        if _is_trn_token(tok) or _looks_like_date_token(tok):
            continue
        out.append(tok)
    return out


def extract_invoice_number(text: str) -> tuple[str | None, float, int | None]:
    """Return (invoice_number, confidence, line_no). Scans for labelled numbers first
    (ranked by label specificity), then a bare INV-style reference."""
    lines = text.splitlines()
    best: tuple[int, str, int] | None = None  # (score, value, line_no)
    for i, raw in enumerate(lines):
        norm = _norm_label(raw)
        if not norm:
            continue
        label_score = 0
        for lbl, sc in _INV_NUM_LABELS:
            if lbl in norm:
                label_score = sc
                break
        if label_score == 0:
            continue
        is_negative = any(neg in norm for neg in _NEG_NUM_LABELS)
        tokens = _num_tokens(raw)
        ev_line = i
        if not tokens and i + 1 < len(lines):
            tokens = _num_tokens(lines[i + 1])
            ev_line = i + 1
        for tok in tokens:
            has_letter_or_sep = bool(re.search(r"[A-Za-z/._-]", tok))
            # A bare number (e.g. "437" from an amount) is only a plausible invoice
            # number under a strong, specific label — never a weak/negative one.
            if not has_letter_or_sep and (is_negative or label_score < 8):
                continue
            score = label_score - (6 if is_negative else 0)
            if has_letter_or_sep:
                score += 1  # invoice numbers usually have a prefix/separator
            if best is None or score > best[0]:
                best = (score, tok, ev_line)
    if best and best[0] > 0:
        conf = 0.97 if best[0] >= 9 else 0.9 if best[0] >= 6 else 0.75
        return best[1], conf, best[2]
    # Fallback: a bare INV-style reference anywhere (e.g. "CMW/INV.76-26").
    m = _INV_REF_RE.search(text)
    if m:
        return m.group(1).strip(), 0.6, None
    return None, 0.0, None


# Date labels: invoice-issuance labels (scored) and other dates we must NOT confuse.
_INV_DATE_LABELS: list[tuple[str, int]] = [
    ("taxinvoicedate", 10), ("invoicedate", 9), ("billdate", 8),
    ("dateofissue", 7), ("issuedate", 7), ("issuedon", 7), ("date", 3),
]
_OTHER_DATE_LABELS = (
    "duedate", "paymentdue", "dueon", "supplydate", "dateofsupply", "taxpoint",
    "deliverydate", "podate", "purchaseorderdate", "contractdate", "paymentdate",
)
_MONTHS_FULL = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def normalize_date(raw: str) -> tuple[str | None, str]:
    """Normalise a displayed date to ISO (YYYY-MM-DD), preserving the original text.
    Defaults to day-first (UAE/international), but respects an unambiguous order
    (a first part > 12 ⇒ day-first; a middle part > 12 ⇒ month-first)."""
    original = raw.strip()
    s = original
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)  # ISO
    if m:
        y, mo, d = map(int, m.groups())
        return _iso(y, mo, d), original
    # Written month: "24 July 2026" or "July 24, 2026"
    m = re.search(rf"(\d{{1,2}})\s*({_MONTHS})[a-z]*\.?\s*,?\s*(\d{{2,4}})", s, re.I)
    if m:
        d, mon, y = int(m.group(1)), _MONTHS_FULL[m.group(2)[:3].lower()], int(m.group(3))
        return _iso(_yr(y), mon, d), original
    m = re.search(rf"({_MONTHS})[a-z]*\.?\s*(\d{{1,2}})\s*,?\s*(\d{{2,4}})", s, re.I)
    if m:
        mon, d, y = _MONTHS_FULL[m.group(1)[:3].lower()], int(m.group(2)), int(m.group(3))
        return _iso(_yr(y), mon, d), original
    # Numeric d/m/y (or m/d/y): decide day-first vs month-first from the values.
    m = re.search(r"(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{2,4})", s)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(1).__len__() == 4:            # YYYY/MM/DD
            return _iso(a, b, c), original
        if a > 12 >= b or a > 31:                 # clearly day-first
            return _iso(_yr(c), b, a), original
        if b > 12:                                # middle > 12 ⇒ month-first
            return _iso(_yr(c), a, b), original
        return _iso(_yr(c), b, a), original       # default day-first (UAE)
    return None, original


def _yr(y: int) -> int:
    return y + 2000 if y < 100 else y


def _iso(y: int, mo: int, d: int) -> str | None:
    try:
        from datetime import date

        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def extract_dates(text: str) -> dict[str, object]:
    """Classify dates on the document. Returns invoice_date (ISO), its original text,
    confidence, line_no, plus due/supply dates so they are never mistaken for it."""
    lines = text.splitlines()
    inv_best: tuple[int, str, int] | None = None       # (score, raw_date, line_no)
    due = supply = None
    for i, raw in enumerate(lines):
        norm = _norm_label(raw)
        dm = _DATE_RE.search(_ARABIC_RE.sub(" ", raw))
        if not dm:
            continue
        raw_date = dm.group(1)
        other = next((o for o in _OTHER_DATE_LABELS if o in norm), None)
        if other:
            if other in ("duedate", "paymentdue", "dueon") and not due:
                due = raw_date
            elif other in ("supplydate", "dateofsupply", "taxpoint", "deliverydate") and not supply:
                supply = raw_date
            continue  # never treat a due/supply/PO date as the invoice date
        score = 0
        for lbl, sc in _INV_DATE_LABELS:
            if lbl in norm:
                score = sc
                break
        if score and (inv_best is None or score > inv_best[0]):
            inv_best = (score, raw_date, i)
    # Fallback: first plain date if nothing was labelled as an invoice date.
    if inv_best is None:
        for i, raw in enumerate(lines):
            dm = _DATE_RE.search(_ARABIC_RE.sub(" ", raw))
            if dm and not any(o in _norm_label(raw) for o in _OTHER_DATE_LABELS):
                inv_best = (0, dm.group(1), i)
                break
    out: dict[str, object] = {"invoice_date": None, "original": None, "confidence": 0.0,
                              "line_no": None, "due": None, "supply": None}
    if inv_best:
        iso, original = normalize_date(inv_best[1])
        out.update(invoice_date=iso or original, original=original, line_no=inv_best[2],
                   confidence=0.9 if inv_best[0] >= 7 else 0.6)
    if due:
        out["due"] = normalize_date(due)[0] or due
    if supply:
        out["supply"] = normalize_date(supply)[0] or supply
    return out


# ── columnar layout recovery ─────────────────────────────────────────────────
# Some scanned invoices OCR into two blocks: all the field LABELS first, then all the
# VALUES together (often with a product table in between). The label-adjacent parsers
# then miss everything. This recovers those fields by pairing the labels to the value
# block positionally, validated by type so intervening noise lines are skipped.
_COL_LABELS: list[tuple[str, str]] = [
    ("invoicedate", "date"), ("taxinvoicedate", "date"),
    ("invoiceno", "ref"), ("invoicenumber", "ref"), ("taxinvoiceno", "ref"), ("billno", "ref"),
    ("clientname", "name"), ("customername", "name"), ("customer", "name"),
    ("client", "name"), ("billto", "name"), ("soldto", "name"),
]


def _value_of_type(s: str, typ: str) -> str | None:
    s = s.strip(" :.-")
    if not s:
        return None
    if typ == "date":
        m = _DATE_RE.search(_ARABIC_RE.sub(" ", s))
        return m.group(1) if m else None
    if typ == "ref":
        toks = _num_tokens(s)
        for t in toks:
            if re.search(r"[A-Za-z]", t) and re.search(r"\d", t):  # letters + digits
                return t
        return None
    if typ == "name":
        clean = _ARABIC_RE.sub(" ", s).strip()
        letters = sum(ch.isalpha() for ch in clean)
        # A name: mostly letters, at least two words or a company suffix, not a pure code.
        if letters >= 4 and (" " in clean or _COMPANY_SUFFIX.search(clean)) and not clean[:1].isdigit():
            return _clean_party_name(clean)
        return None
    return None


def _is_supplier_fragment(name: str | None, supplier: str | None) -> bool:
    """True if `name` looks like a mid-word fragment of the supplier's name — e.g.
    "ADING L.L.C" cut out of "…TRADING L.L.C"."""
    if not name or not supplier:
        return False
    words = re.sub(r"[^a-z ]", " ", name.lower()).split()
    if not words:
        return False
    first = words[0]
    if len(first) < 4:
        return False
    sup = supplier.lower()
    idx = sup.find(first)
    return idx > 0 and sup[idx - 1].isalpha()   # found, but preceded by a letter (mid-word)


def _columnar_extract(text: str) -> dict:
    """Recover invoice_number / invoice_date / customer name+address for two-block
    (labels-then-values) OCR layouts. Returns only what it can pair confidently."""
    lines = [ln.strip() for ln in text.splitlines()]
    labels: list[tuple[int, str]] = []  # (line_index, type)
    for i, ln in enumerate(lines):
        head = _norm_label(ln.split(":")[0]) if ":" in ln else _norm_label(ln)
        val = ln.split(":", 1)[1].strip() if ":" in ln else ""
        for key, typ in _COL_LABELS:
            if head == key or head.startswith(key):
                if not _value_of_type(val, typ):     # only unpaired labels (value elsewhere)
                    labels.append((i, typ))
                break
    if len(labels) < 2:
        return {}

    # Multi-page documents repeat the labels; keep only the FIRST contiguous group so we
    # pair against the value block on the same page.
    first_line = labels[0][0]
    labels = [lab for lab in labels if lab[0] - first_line <= 15]

    # Value block: non-empty, non-label lines after the last label. Skip pure-number
    # rows (product codes / row numbers) but KEEP dates (also all-digits/slashes).
    start = labels[-1][0] + 1
    values: list[str] = []
    for ln in lines[start:start + 60]:
        if not ln or ":" in ln:
            continue
        if re.fullmatch(r"[\d\s.,/-]+", ln) and not _DATE_RE.search(ln):
            continue
        values.append(ln)

    # Positional, type-matched pairing with a NON-consuming cursor: for each label find
    # the next value (from the cursor) matching its type; a label with no match doesn't
    # consume the values meant for later labels.
    out: dict = {}
    cursor = 0
    field_for = {"date": "invoice_date", "ref": "invoice_number", "name": "recipient_name"}
    for _, typ in labels:
        j = cursor
        while j < len(values):
            got = _value_of_type(values[j], typ)
            if got:
                key = field_for.get(typ)
                if key and key not in out:
                    out[key] = got
                    if typ == "name":
                        addr = []
                        for a in values[j + 1: j + 3]:
                            if _value_of_type(a, "ref") or _value_of_type(a, "date"):
                                break
                            addr.append(a)
                        if addr:
                            out["recipient_address"] = ", ".join(addr)
                cursor = j + 1
                break
            j += 1
    return out


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

    # Invoice number — robust, label-scored, bilingual/colon-less tolerant.
    num, num_conf, _num_line = extract_invoice_number(text)
    if num:
        inv.invoice_number = num
        set_conf("invoice_number", num_conf)

    # Dates — classify the invoice date vs due/supply dates; normalise to ISO while
    # preserving the original displayed text. Never picks a due/supply/PO date.
    dates = extract_dates(text)
    if dates["invoice_date"]:
        inv.invoice_date = str(dates["invoice_date"])
        inv.invoice_date_original = dates["original"]  # type: ignore[assignment]
        set_conf("invoice_date", float(dates["confidence"]))  # type: ignore[arg-type]
    if dates["due"]:
        inv.due_date = str(dates["due"])
        set_conf("due_date", 0.8)
    if dates["supply"]:
        inv.supply_date = str(dates["supply"])
        set_conf("supply_date", 0.8)

    # Columnar-layout recovery: some scans OCR all labels first, then all values (with a
    # product table between). Pair them positionally to recover fields the adjacent
    # parsers missed. `col` is reused for the customer name/address below.
    col = _columnar_extract(text)
    if not inv.invoice_number and col.get("invoice_number"):
        inv.invoice_number = col["invoice_number"]
        set_conf("invoice_number", 0.7)
    if not inv.invoice_date and col.get("invoice_date"):
        _iso, _orig = normalize_date(col["invoice_date"])
        inv.invoice_date = _iso or _orig
        inv.invoice_date_original = _orig
        set_conf("invoice_date", 0.65)

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
    # Columnar override: prefer the positionally-paired customer when the adjacent parse
    # missed it or returned a mid-word fragment of the supplier (e.g. "ADING" ← "TRADING").
    col_name = col.get("recipient_name")
    if col_name and (not recipient.name or _is_supplier_fragment(recipient.name, supplier.name)):
        recipient.name = _clean_party_name(col_name)
        set_conf("recipient.name", 0.75)
        if col.get("recipient_address"):
            recipient.address = col["recipient_address"]
            set_conf("recipient.address", 0.65)

    # Recipient address — prefer a customer-specific label, else the address block that
    # sits next to the customer's name; never silently borrow the supplier's address.
    addr = _first_label(labels, "customeraddress", "billingaddress", "clientaddress", "shiptoaddress")
    if addr:
        recipient.address = addr
        set_conf("recipient.address", 0.75)
    elif recipient.name:
        near = _address_near_name(text, recipient.name, supplier.address)
        if near:
            recipient.address = near
            set_conf("recipient.address", 0.6)
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

    # Explicit zero-rated / 0% VAT is a valid 0% taxable supply — VAT is 0. Detect it
    # so a spurious net+vat=gross triple (e.g. a line's unit-price columns) can't invent
    # a non-zero VAT on a document that clearly states 0%.
    zero_rated = vat_rate is not None and vat_rate == 0
    if not zero_rated:
        zero_rated = bool(
            re.search(r"\bVAT\b[^%\n]{0,10}\b0(?:\.0+)?\s*%|\b0(?:\.0+)?\s*%\s*VAT|zero[\s-]?rated", text, re.I)
        )
    if zero_rated:
        inv.has_zero_rated_statement = True

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

    if zero_rated and amounts:
        # 0% supply: the grand total is the largest money amount; net = gross, VAT = 0.
        total = max(amounts)
        inv.total_net, inv.total_vat, inv.total_gross = total, Decimal("0"), total
        inv.treatment = VatTreatment.ZERO_RATED
        for _f in ("total_net", "total_vat", "total_gross"):
            set_conf(_f, 0.7)
    elif candidates:
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

    # Assess each party's geography & UAE-VAT status (outside-UAE aware): sets
    # country, is_uae and vat_registration_status on supplier and recipient.
    from ..vat.parties import assess_party

    assess_party(inv.supplier)
    assess_party(inv.recipient)
    if inv.supplier.country:
        set_conf("supplier.country", 0.7)
    if inv.recipient.country:
        set_conf("recipient.country", 0.7)

    inv.field_confidence = conf
    inv.field_evidence = _build_evidence(text, inv)
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
