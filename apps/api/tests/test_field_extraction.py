"""Tests for the generic, layout-agnostic invoice field parser.

Uses OCR-style text with collapsed spacing (as real OCR produces) to prove the parser
is not tuned to one clean template.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.field_extraction import classify, parse_invoice
from app.vat.schemas import InvoiceType

# Mirrors the real scanned CITIC tax invoice after OCR (spaces often dropped).
OCR_TEXT = """\
CITICMIDDLEEASTCONTRACTINGL.L.C
Hessa Street,I Rise Tower, No: 26C-01
TRN:105110997100003
Tax Invoice
CustomerEnglishLegalName:MAGPARKREALESTATEDEVELOPMENTL.L.C-FZ
TaxInvoiceNumber:CMECLLC20260701
CustomerTRN:104215659400003
DATE:9/7/2026
RegisteredAddress:Business Center 1, M Floor, The Meydan H, Dubai
VAT 5%
26,050,000.00
1,302,500.00
27,352,500.00
7,700,000.00
385,000.00
8,085,000.00
TOTAL
33,750,000.00
1,687,500.00
35,437,500.00
BankName:First Abu Dhabi Bank
AccountNumber:4031006919499001
IBAN:AE390354031006919499001
SwiftCode:NBADAEAAXXX
"""


def test_classify_tax_invoice():
    assert classify(OCR_TEXT) == InvoiceType.TAX_INVOICE
    assert classify("CREDIT NOTE for return") == InvoiceType.CREDIT_NOTE
    assert classify("Cash Receipt") == InvoiceType.RECEIPT


def test_parse_core_fields():
    inv = parse_invoice(OCR_TEXT)
    assert inv.invoice_number == "CMECLLC20260701"
    assert inv.invoice_date == "9/7/2026"
    assert inv.supplier.trn == "105110997100003"
    assert inv.recipient.trn == "104215659400003"
    assert "MAGPARK" in (inv.recipient.name or "")
    assert inv.currency == "AED"


def test_parse_totals_via_triple_solver():
    inv = parse_invoice(OCR_TEXT)
    assert inv.total_net == Decimal("33750000.00")
    assert inv.total_vat == Decimal("1687500.00")
    assert inv.total_gross == Decimal("35437500.00")


def test_parse_line_items_are_rate_consistent():
    inv = parse_invoice(OCR_TEXT)
    # Two genuine rows recovered; spurious sum-triples excluded by the rate filter.
    assert len(inv.line_items) == 2
    for li in inv.line_items:
        assert li.vat_amount == (li.net_amount * Decimal("0.05")).quantize(Decimal("0.01"))


def test_parse_payment_info():
    inv = parse_invoice(OCR_TEXT)
    assert inv.payment is not None
    assert inv.payment.iban == "AE390354031006919499001"
    assert inv.payment.account_number == "4031006919499001"
    assert inv.payment.swift == "NBADAEAAXXX"


def test_confidence_scores_present():
    inv = parse_invoice(OCR_TEXT)
    assert inv.field_confidence.get("invoice_number", 0) > 0.5
    assert inv.field_confidence.get("total_gross", 0) > 0.5


# Mirrors the scanned MMRC→Keturah invoice: a month-name-first date with NO label,
# and a customer under a "To," block whose OCR line merged with the right column.
KETURAH_OCR = """\
Mohammed MunafRoad ContractingLLC
R-01,Abdulla Khalifa Building,Qusais Ind Area 2|P.O.Box:19678,Dubai-UAE
Tax Invoice
July 24, 2026
To, InvoiceNo:MMRC/Inv/2026/53
Keturah Lifescaping LLC TRN:100384864300003
Dubai,UAE.
TRN:
Gross Total 368,735.30
5%VAT 18,436.77
NetTotalAED:Three Hundred Eighty-Seven Thousand 387,172.07
"""


def test_month_name_date_and_to_block_customer():
    inv = parse_invoice(KETURAH_OCR)
    # Month-name-first date with no label is detected.
    assert inv.invoice_date == "July 24, 2026"
    # Customer under a "To," block — distinct from the supplier.
    assert "Keturah Lifescaping" in (inv.recipient.name or "")
    assert "Mohammed Munaf" in (inv.supplier.name or "")
    assert inv.recipient.name != inv.supplier.name
    # Totals recovered from reversed labels ("Gross Total" = net, "Net Total" = gross).
    assert inv.total_net == Decimal("368735.30")
    assert inv.total_vat == Decimal("18436.77")
    assert inv.total_gross == Decimal("387172.07")


def test_vat_inclusive_single_total():
    inv = parse_invoice("Grand Total: AED 105,000.00 inclusive of 5% VAT")
    assert inv.total_gross == Decimal("105000.00")
    assert inv.total_net == Decimal("100000.00")
    assert inv.total_vat == Decimal("5000.00")


def test_vat_exclusive_single_total():
    inv = parse_invoice("Subtotal 200,000.00 plus VAT 5%")
    assert inv.total_net == Decimal("200000.00")
    assert inv.total_vat == Decimal("10000.00")
    assert inv.total_gross == Decimal("210000.00")


def test_various_date_formats():
    for text, expected in [
        ("Date: 2026-07-24", "2026-07-24"),
        ("Invoice Date: 24/07/2026", "24/07/2026"),
        ("Dated 24 July 2026", "24 July 2026"),
        ("Issued on Aug 3, 2026", "Aug 3, 2026"),
    ]:
        assert parse_invoice(text).invoice_date == expected
