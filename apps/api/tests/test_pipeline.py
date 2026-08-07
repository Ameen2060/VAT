"""End-to-end smoke test for the Phase 1 pipeline using the offline stub provider.

Verifies upload → extraction → rule engine → advisory → persistence → report,
without needing an AI key or external services.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

SAMPLE_INVOICE = b"""\
TAX INVOICE
Invoice No: INV-2026-0007
Date: 2026-08-01
Supplier TRN: 100123456700003
Description: Consulting services
Net: 1000.00
VAT (5%): 50.00
Total: 1050.00
"""


def test_upload_review_and_report_flow():
    with TestClient(app) as client:
        # health
        assert client.get("/health").json()["status"] == "ok"

        # upload a text invoice
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("invoice.txt", SAMPLE_INVOICE, "text/plain")},
            data={"category": "invoice"},
        )
        assert resp.status_code == 200, resp.text
        summaries = resp.json()
        assert len(summaries) == 1
        review_id = summaries[0]["review_id"]
        # A missing supplier name is an extraction gap, NOT a compliance failure: it
        # must not fail the invoice on its own (no genuine violation in this sample).
        assert summaries[0]["compliance_status"] == "pass"

        # detail: verification items surface the un-extracted fields transparently
        detail = client.get(f"/api/reviews/{review_id}").json()
        assert detail["invoice"]["supplier"]["trn"] == "100123456700003"
        assert "findings" in detail["result"]
        assert detail["result"]["requires_verification"] is True
        verify_fields = {v["field"] for v in detail["result"]["verification_items"]}
        assert "supplier.name" in verify_fields

        # approval workflow
        upd = client.patch(f"/api/reviews/{review_id}/status", json={"status": "approved"})
        assert upd.json()["status"] == "approved"

        # dashboard aggregates
        dash = client.get("/api/dashboard").json()
        assert dash["total_reviews"] >= 1

        # report (HTML always available)
        html = client.get(f"/api/reviews/{review_id}/report?format=html")
        assert html.status_code == 200
        assert "UAE VAT Compliance Report" in html.text


def test_structured_review_endpoint():
    with TestClient(app) as client:
        payload = {
            "invoice_type": "tax_invoice",
            "invoice_number": "INV-1",
            "invoice_date": "2026-08-01",
            "supplier": {"name": "ACME", "address": "Dubai", "trn": "100123456700003"},
            "recipient": {"name": "Buyer", "address": "Dubai", "trn": "100999888700003"},
            "transaction_type": "local",
            "treatment": "standard",
            "currency": "AED",
            "total_net": "1000.00",
            "total_vat": "50.00",
            "total_gross": "1050.00",
            "has_tax_invoice_label": True,
            "line_items": [
                {
                    "description": "Consulting",
                    "net_amount": "1000.00",
                    "vat_rate": "0.05",
                    "vat_amount": "50.00",
                    "treatment": "standard",
                }
            ],
        }
        resp = client.post("/api/review", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["compliance_status"] == "pass"
        assert body["risk_level"] == "low"
