"""Tests for the VAT201 return generator: classification, aggregation, endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

# A mixed period: standard sales (2 emirates), zero, exempt, standard purchase,
# reverse-charge purchase, and an import.
CSV = b"""Date,Type,Party,Invoice No,TRN,Emirate,Tax Code,Rate,Taxable Amount,VAT Amount
2026-07-05,Sales Invoice,Cust A,INV-1,100123456700003,Dubai,SR,5%,100000,5000
2026-07-06,Sales Invoice,Cust B,INV-2,,Abu Dhabi,SR,5%,50000,2500
2026-07-07,Sales Invoice,Export Co,INV-3,,,ZR,0%,20000,0
2026-07-08,Sales Invoice,Clinic,INV-4,,,EX,0%,10000,0
2026-07-10,Purchase Bill,Supplier X,BILL-1,,,SR,5%,40000,2000
2026-07-11,Purchase Bill,Overseas Ltd,BILL-2,,,RC,5%,8000,400
2026-07-12,Import,Customs,IMP-1,,,IM,5%,30000,1500
2026-04-01,Sales Invoice,Old Period,INV-OLD,,Dubai,SR,5%,999999,49999
"""


def _boxes(ret: dict) -> dict[str, dict]:
    return {b["box"]: b for b in ret["boxes"]}


def test_generate_classifies_and_totals():
    with TestClient(app) as client:
        resp = client.post(
            "/api/vat201/generate",
            files={"file": ("txns.csv", CSV, "text/csv")},
            data={"company_name": "Keturah LLC", "company_trn": "100999888700003",
                  "period_type": "quarter", "year": "2026", "index": "3"},
        )
        assert resp.status_code == 200, resp.text
        ret = resp.json()["return"]
        b = _boxes(ret)

        # Standard sales allocated to the right emirate boxes.
        assert b["1b"]["amount"] == "100000.00" and b["1b"]["vat"] == "5000.00"  # Dubai
        assert b["1a"]["amount"] == "50000.00" and b["1a"]["vat"] == "2500.00"   # Abu Dhabi
        assert b["4"]["amount"] == "20000.00"   # zero-rated
        assert b["5"]["amount"] == "10000.00"   # exempt
        assert b["6"]["vat"] == "1500.00"        # imports
        assert b["3"]["vat"] == "400.00"         # reverse-charge self-assessed output
        assert b["10"]["vat"] == "400.00"        # reverse-charge recoverable

        # Out-of-period row (April) excluded from a Q3 return.
        assert "999999" not in str(ret["boxes"])

        # Net: output 9400 (7500 std + 400 RCM + 1500 import) − recoverable 3900
        # (2000 std + 1500 import + 400 RCM) = 5500 payable.
        assert ret["totals"]["output_vat"] == "9400.00"
        assert ret["totals"]["recoverable_input_vat"] == "3900.00"
        assert ret["totals"]["net_vat_due"] == "5500.00"
        assert ret["totals"]["is_refund"] is False
        assert ret["period_label"] == "2026-Q3"
        assert ret["due_date"] == "2026-10-28"


def test_drilldown_and_export():
    with TestClient(app) as client:
        resp = client.post(
            "/api/vat201/generate",
            files={"file": ("txns.csv", CSV, "text/csv")},
            data={"period_type": "quarter", "year": "2026", "index": "3"},
        )
        rid = resp.json()["id"]

        # Drill-down: box 1a has exactly the Abu Dhabi sale.
        d = client.get(f"/api/vat201/returns/{rid}/transactions", params={"box": "1a"}).json()
        assert len(d) == 1 and d[0]["invoice_number"] == "INV-2"

        # Exports return the right content types.
        assert client.get(f"/api/vat201/returns/{rid}/export?format=csv").headers["content-type"].startswith("text/csv")
        pdf = client.get(f"/api/vat201/returns/{rid}/export?format=pdf")
        assert pdf.content[:5] == b"%PDF-"
        xlsx = client.get(f"/api/vat201/returns/{rid}/export?format=xlsx")
        assert xlsx.status_code == 200 and len(xlsx.content) > 500


def test_totals_row_is_excluded():
    """A 'Total' row (or a row with amounts but no invoice/party) must NOT be counted
    as a transaction — otherwise every figure doubles."""
    csv = b"""Date,Type,Party,Invoice No,Emirate,Tax Code,Rate,Taxable Amount,VAT Amount
2026-08-05,Sales Invoice,Cust A,INV-1,Dubai,SR,5%,100000,5000
2026-08-06,Sales Invoice,Cust B,INV-2,Dubai,SR,5%,50000,2500
Total,,,,,,,150000,7500
"""
    with TestClient(app) as client:
        resp = client.post(
            "/api/vat201/generate",
            files={"file": ("t.csv", csv, "text/csv")},
            data={"period_type": "month", "year": "2026", "index": "8"},
        )
        b = _boxes(resp.json()["return"])
        assert b["1b"]["amount"] == "150000.00"  # not 300000
        assert b["1b"]["vat"] == "7500.00"       # not 15000
        assert b["1b"]["count"] == 2


def test_default_emirate_when_no_column():
    """Standard-rated sales with no Emirate column go to the chosen default Emirate box."""
    csv = b"""Date,Type,Party,Invoice No,Tax Code,Rate,Taxable Amount,VAT Amount
2026-08-01,Sales Invoice,Cust A,INV-1,SR,5%,100000,5000
"""
    with TestClient(app) as client:
        resp = client.post(
            "/api/vat201/generate",
            files={"file": ("e.csv", csv, "text/csv")},
            data={"period_type": "month", "year": "2026", "index": "8", "default_emirate": "sharjah"},
        )
        b = _boxes(resp.json()["return"])
        assert b["1c"]["amount"] == "100000.00"  # Sharjah (Box 1c)
        assert b["1b"]["amount"] == "0.00"        # not silently defaulted to Dubai
        # No missing-emirate warning once a default is applied.
        codes = {v["code"] for v in resp.json()["return"]["validations"]}
        assert "MISSING_EMIRATE" not in codes


def test_vat311_refund_application():
    """A return in a refund position can produce a VAT311 refund application + PDF."""
    refund_csv = b"""Date,Type,Party,Invoice No,Emirate,Tax Code,Rate,Taxable Amount,VAT Amount
2026-08-01,Sales Invoice,Cust,INV-1,Dubai,SR,5%,10000,500
2026-08-02,Purchase Bill,Supplier,BILL-1,,SR,5%,200000,10000
"""
    with TestClient(app) as client:
        gen = client.post(
            "/api/vat201/generate",
            files={"file": ("r.csv", refund_csv, "text/csv")},
            data={"company_trn": "100999888700003", "period_type": "month", "year": "2026", "index": "8"},
        ).json()
        assert gen["return"]["totals"]["is_refund"] is True
        assert gen["return"]["totals"]["net_vat_due"] == "9500.00"
        rid = gen["id"]

        # Prepare VAT311 (request full amount).
        app_ = client.post(
            f"/api/vat201/returns/{rid}/refund311",
            json={"amount_requested": 9500, "authorized_signatory": "A. Salouaa"},
        ).json()
        assert app_["total_excess_refundable"] == "9500.00"
        assert app_["amount_requested"] == "9500.00"
        assert app_["remaining_excess"] == "0.00"
        assert app_["net_refund_expected"] == "9500.00"

        # Export the VAT311 PDF.
        pdf = client.get(f"/api/vat201/returns/{rid}/refund311/export")
        assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"


def test_vat311_rejected_when_payable():
    """A payable return cannot produce a VAT311 refund application."""
    payable = b"""Date,Type,Party,Invoice No,Emirate,Tax Code,Rate,Taxable Amount,VAT Amount
2026-08-01,Sales Invoice,Cust,INV-1,Dubai,SR,5%,100000,5000
"""
    with TestClient(app) as client:
        rid = client.post(
            "/api/vat201/generate",
            files={"file": ("p.csv", payable, "text/csv")},
            data={"period_type": "month", "year": "2026", "index": "8"},
        ).json()["id"]
        resp = client.post(f"/api/vat201/returns/{rid}/refund311", json={})
        assert resp.status_code == 400


def test_validation_flags_invalid_trn_and_missing_emirate():
    bad = b"""Date,Type,Party,Emirate,Tax Code,Rate,Taxable Amount,VAT Amount,TRN
2026-08-01,Sales Invoice,X,,SR,5%,1000,50,12345
"""
    with TestClient(app) as client:
        resp = client.post(
            "/api/vat201/generate",
            files={"file": ("b.csv", bad, "text/csv")},
            data={"period_type": "month", "year": "2026", "index": "8"},
        )
        codes = {v["code"] for v in resp.json()["return"]["validations"]}
        assert "INVALID_TRN" in codes
        assert "MISSING_EMIRATE" in codes
