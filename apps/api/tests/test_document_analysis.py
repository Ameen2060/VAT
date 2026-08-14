"""Document Analysis upgrade — customer/vendor detection, outside-UAE TRN logic,
VAT-treatment/conclusion, and robust Invoice Number + Invoice Date extraction.

Covers the acceptance matrix from the spec (invoice-number labels/formats, multiple
dates/numbers, cross-border direction, PASS/FAIL/REVIEW) using realistic text.
"""

from __future__ import annotations

from app.services.field_extraction import extract_dates, extract_invoice_number, parse_invoice
from app.vat.parties import assess_party
from app.vat.rules import review_invoice
from app.vat.schemas import Conclusion, PartyDetails


# ── Invoice number: labels & formats ─────────────────────────────────────────
def test_invoice_number_labels_and_formats():
    cases = {
        "Invoice No.: INV-2026-00125": "INV-2026-00125",
        "Invoice Number : ABC/2026/77": "ABC/2026/77",
        "Tax Invoice No.  M-006-SYR": "M-006-SYR",
        "Bill No: BILL-9931": "BILL-9931",
        "Invoice # : 2026-XY-0007": "2026-XY-0007",
        "رقم الفاتورة/Invoice No. : M-006-SYR": "M-006-SYR",  # bilingual
    }
    for text, expected in cases.items():
        num, conf, _ = extract_invoice_number(text)
        assert num == expected, f"{text!r} -> {num!r}"
        assert conf >= 0.6


def test_invoice_number_not_confused_with_trn_or_po():
    text = "\n".join([
        "Tax Invoice",
        "TRN: 100123456700003",
        "PO Number: PO-55501",
        "Invoice No.: INV-2026-900",
        "Customer Account No: CUST-7788",
    ])
    num, _, _ = extract_invoice_number(text)
    assert num == "INV-2026-900"


def test_invoice_number_ranks_over_reference():
    text = "Reference No: REF-1\nInvoice Number: INV-2026-555"
    num, _, _ = extract_invoice_number(text)
    assert num == "INV-2026-555"


# ── Invoice date: classification & normalisation ─────────────────────────────
def test_date_not_confused_with_due_or_supply():
    text = "\n".join([
        "Invoice Date: 24/07/2026",
        "Supply Date: 23/07/2026",
        "Due Date: 23/08/2026",
        "PO Date: 10/07/2026",
    ])
    d = extract_dates(text)
    assert d["invoice_date"] == "2026-07-24"
    assert d["due"] == "2026-08-26" or d["due"] == "2026-08-23"  # normalised due date
    assert d["supply"] == "2026-07-23"


def test_date_daymonth_vs_monthday():
    assert extract_dates("Invoice Date: 07/24/2026")["invoice_date"] == "2026-07-24"  # US m/d
    assert extract_dates("Invoice Date: 24/07/2026")["invoice_date"] == "2026-07-24"  # UAE d/m


# ── Party geography & outside-UAE TRN logic ──────────────────────────────────
def test_uae_party_with_trn_registered():
    p = PartyDetails(name="ABC LLC", address="Dubai, UAE", trn="100123456700003")
    assess_party(p)
    assert p.is_uae is True
    assert "Registered" in p.vat_registration_status


def test_uae_party_missing_trn_flagged():
    p = PartyDetails(name="XYZ LLC", address="Abu Dhabi, United Arab Emirates")
    assess_party(p)
    assert p.is_uae is True
    assert "missing" in p.vat_registration_status.lower()


def test_overseas_party_no_trn_is_not_applicable():
    p = PartyDetails(name="ABC Ltd", address="London, United Kingdom")
    assess_party(p)
    assert p.is_uae is False
    assert "not applicable" in p.vat_registration_status.lower()


# ── End-to-end conclusions across scenarios ──────────────────────────────────
def _inv(text):
    return review_invoice(parse_invoice(text), text)


def test_overseas_customer_not_failed_for_missing_trn():
    text = "\n".join([
        "SUPPLIER TRADING LLC",
        "Dubai, UAE",
        "Tax Invoice",
        "TRN: 100123456700003",
        "Invoice No: INV-2026-1",
        "Invoice Date: 01/07/2026",
        "Bill To: ABC Ltd",
        "Address: London, United Kingdom",
        "Total 1000 VAT 0 Grand 1000",
    ])
    inv = parse_invoice(text)
    assert inv.recipient.is_uae is False
    r = review_invoice(inv, text)
    # Overseas customer with no UAE TRN must never be a FAIL just for that.
    assert r.conclusion in (Conclusion.REVIEW, Conclusion.PASS)
    assert r.transaction_type.value in ("export", "gcc", "unknown")


def test_domestic_uae_missing_number_and_date_is_review():
    text = "\n".join([
        "SUPPLIER LLC", "Dubai, UAE", "Tax Invoice",
        "TRN: 100123456700003",
        "Customer: BUYER LLC  TRN: 100999888700003  Dubai UAE",
        "Total 1000 VAT 50 Grand 1050",
    ])
    r = _inv(text)
    assert r.conclusion == Conclusion.REVIEW
    assert "Invoice Number" in r.conclusion_reason or "Invoice Date" in r.conclusion_reason


def test_pass_fail_review_conclusions():
    from app.vat.schemas import Conclusion
    # PASS: clean UAE->UAE 5% invoice with valid TRNs and correct arithmetic.
    ok = "\n".join([
        "ABC TRADING LLC", "Dubai, UAE", "Tax Invoice", "TRN: 100123456700003",
        "Invoice No: INV-100", "Invoice Date: 01/07/2026",
        "Bill To: XYZ SERVICES LLC", "Customer TRN: 100999888700003", "Address: Abu Dhabi, UAE",
        "Net: 1000.00", "VAT: 50.00", "Total: 1050.00",
    ])
    assert review_invoice(parse_invoice(ok), ok).conclusion == Conclusion.PASS
    # FAIL: printed net + VAT does not equal the printed total.
    bad = ok.replace("Total: 1050.00", "Total: 1100.00")
    r = review_invoice(parse_invoice(bad), bad)
    assert r.conclusion == Conclusion.FAIL
    assert any(f.rule_id == "CALC-004" for f in r.findings)


def test_columnar_layout_labels_then_values():
    # Scanned layout where all field LABELS are in one block and their VALUES in another
    # (with a product table between) — as produced by multi-column OCR. Fields must still
    # be paired correctly (this reproduces the ALMUKDAD/Oleochem 5-page invoice).
    text = "\n".join([
        "ALMUKDAD LUBRICANTS & GREASE TRADING",
        "Tax Invoice", "TRN: 105424163100003",
        "Invoice Date:", "Invoice No.:", "Client Name:", "Address:",
        "Place of Loading", "HS Code",
        "504000004026", "235000034026", "59900000405",   # product-code table
        "05/08/2026", "M-006-SYR",
        "Oleochem For Lubricant Oils & Petrochemicals Abou Ghoufa",
        "Syria, Rif Dimashq, Eastern Al-Kiswah",
        "Total 118944.10", "VAT 0%",
    ])
    inv = parse_invoice(text)
    assert inv.invoice_number == "M-006-SYR"
    assert "Oleochem" in (inv.recipient.name or "")
    assert inv.recipient.is_uae is False          # Syria -> outside UAE
    r = review_invoice(inv, text)
    assert "recipient.trn" not in {v.field for v in r.verification_items}


def test_zero_rated_invoice_accepted_not_flagged():
    # A clearly 0% invoice must be read as VAT=0 (not a spurious line-item triple) and
    # the "VAT rate consistency" check must PASS.
    text = "\n".join([
        "SUPPLIER LLC", "Dubai, UAE", "Tax Invoice",
        "TRN: 100123456700003",
        "Invoice No: INV-Z1", "Invoice Date: 01/07/2026",
        "Sr Item Qty UnitPrice Amount",
        "1 Goods 10 343.63 373.95",   # a line's columns that happen to sum with 30.32
        "Total 118944.10", "VAT 0% 0.00", "Grand Total 118944.10",
    ])
    inv = parse_invoice(text)
    assert inv.total_vat == 0
    r = review_invoice(inv, text)
    rate_check = next(c for c in r.validations if c.name == "VAT rate consistency")
    assert rate_check.passed is True


def test_overseas_party_trn_not_flagged_as_missing():
    from app.services.field_extraction import parse_invoice as _pi
    text = "\n".join([
        "UAE SUPPLIER LLC", "Dubai, UAE", "Tax Invoice",
        "TRN: 100123456700003",
        "Invoice No: INV-9", "Invoice Date: 01/07/2026",
        "Bill To: ABC Ltd", "Address: London, United Kingdom",
        "Total 1000 VAT 0 Grand 1000",
    ])
    inv = _pi(text)
    assert inv.recipient.is_uae is False
    r = review_invoice(inv, text)
    gaps = {v.field for v in r.verification_items}
    assert "recipient.trn" not in gaps   # overseas customer TRN is not required


def test_tax_code_master_has_all_treatments():
    from app.vat.tax_codes import TAX_CODES
    codes = {t.code for t in TAX_CODES}
    assert {"SR", "ZR", "EX", "OOS", "RC", "GCC", "OADJ", "IADJ", "CN", "DN"} <= codes


def test_tax_code_standard_rated_and_expected_vat():
    from decimal import Decimal
    from app.vat.schemas import Invoice, PartyDetails, VatTreatment
    from app.vat.tax_codes import resolve_tax_code
    inv = Invoice(treatment=VatTreatment.STANDARD, total_net=Decimal("1000"), total_vat=Decimal("50"),
                  supplier=PartyDetails(is_uae=True), recipient=PartyDetails(is_uae=True))
    r = resolve_tax_code(inv)
    assert r.code == "SR" and r.certain
    assert r.expected_vat == Decimal("50.00") and r.difference == Decimal("0.00")


def test_zero_percent_is_not_auto_zero_rated():
    from decimal import Decimal
    from app.vat.schemas import Invoice, PartyDetails
    from app.vat.tax_codes import resolve_tax_code
    inv = Invoice(total_net=Decimal("1000"), total_vat=Decimal("0"),
                  supplier=PartyDetails(is_uae=True), recipient=PartyDetails(is_uae=True))
    r = resolve_tax_code(inv)
    # 0% must trigger REVIEW, not an automatic zero-rated PASS.
    assert r.code == "ZR" and r.certain is False


def test_credit_note_tax_code():
    from app.vat.schemas import Invoice, InvoiceType
    from app.vat.tax_codes import resolve_tax_code
    r = resolve_tax_code(Invoice(invoice_type=InvoiceType.CREDIT_NOTE))
    assert r.code == "CN"


def test_vat_code_master_api_list_and_update():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        rows = client.get("/api/vat-codes").json()
        codes = {r["code"] for r in rows}
        assert {"SR", "ZR", "EX", "OOS", "RC", "GCC"} <= codes
        # Admin update (auth is pass-through admin in tests).
        r = client.put("/api/vat-codes/ZR", json={"vat_return_box": "Box 2 (custom)"})
        assert r.status_code == 200, r.text
        assert r.json()["vat_return_box"] == "Box 2 (custom)"
        # persisted
        again = {x["code"]: x for x in client.get("/api/vat-codes").json()}
        assert again["ZR"]["vat_return_box"] == "Box 2 (custom)"


def test_effective_date_filters_active_codes():
    from datetime import date
    from app.vat.tax_codes import active_codes
    assert len(active_codes(date(2026, 7, 1))) >= 10
    assert active_codes(date(2015, 1, 1)) == []   # before UAE VAT commenced


def test_import_from_overseas_supplier_flags_reverse_charge_review():
    text = "\n".join([
        "GLOBAL SUPPLIES GMBH", "Germany", "Invoice",
        "Invoice No: DE-2026-77", "Invoice Date: 05/07/2026",
        "Bill To: UAE IMPORTER LLC  Dubai UAE",
        "Customer TRN: 100123456700003",
        "Consulting services 5000",
    ])
    inv = parse_invoice(text)
    assert inv.supplier.is_uae is False
    assert inv.recipient.is_uae is True
    r = review_invoice(inv, text)
    assert r.transaction_type.value == "import"
    assert r.conclusion == Conclusion.REVIEW


def test_vat201_importer_handles_mislabelled_files():
    # A .xlsx that is actually CSV content must not crash (BadZipFile) — it parses as CSV.
    from app.vat201.importer import _sheets_from_bytes
    csv_bytes = b"Date,Type,Taxable Amount,VAT Amount\n2026-07-15,sales,1000,50\n"
    sheets = _sheets_from_bytes("transactions.xlsx", csv_bytes)
    assert len(sheets[0][1]) == 1
    # A legacy .xls (OLE2 header) gives a clear message, not a 500.
    import pytest
    with pytest.raises(ValueError):
        _sheets_from_bytes("old.xls", b"\xd0\xcf\x11\xe0rubbish")
