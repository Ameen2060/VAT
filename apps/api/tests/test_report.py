"""Tests for the combined PDF report: generation, storage, association, download."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

SAMPLE = b"""\
TAX INVOICE
Invoice No: RPT-2026-1
Date: 2026-08-01
Supplier: Reporte Trading LLC
Supplier TRN: 100123456700003
Customer TRN: 100999888700003
Net: 2000.00
VAT (5%): 100.00
Total: 2100.00
"""


def _upload(client) -> str:
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("rpt.txt", SAMPLE, "text/plain")},
        data={"category": "invoice"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()[0]["review_id"]


def test_generate_store_and_download_report():
    with TestClient(app) as client:
        rid = _upload(client)

        # Not generated yet.
        assert client.get(f"/api/reviews/{rid}").json()["has_report"] is False

        # Generate + store.
        gen = client.post(f"/api/reviews/{rid}/report/generate")
        assert gen.status_code == 200, gen.text
        assert gen.json()["has_report"] is True
        assert gen.json()["report_generated_at"]

        # Now associated with the review and persisted.
        detail = client.get(f"/api/reviews/{rid}").json()
        assert detail["has_report"] is True
        assert detail["report_generated_at"]

        # Download the stored PDF.
        dl = client.get(f"/api/reviews/{rid}/report/file")
        assert dl.status_code == 200
        assert dl.headers["content-type"] == "application/pdf"
        assert dl.content[:5] == b"%PDF-"
        assert len(dl.content) > 1500  # a real multi-section document


def test_report_generates_on_demand_if_missing():
    with TestClient(app) as client:
        rid = _upload(client)
        # Download without explicit generate → should generate + store, then serve.
        dl = client.get(f"/api/reviews/{rid}/report/file")
        assert dl.status_code == 200
        assert dl.content[:5] == b"%PDF-"
        assert client.get(f"/api/reviews/{rid}").json()["has_report"] is True


def test_report_is_per_document():
    with TestClient(app) as client:
        rid1 = _upload(client)
        rid2 = _upload(client)
        client.post(f"/api/reviews/{rid1}/report/generate")
        client.post(f"/api/reviews/{rid2}/report/generate")
        # Distinct stored reports for distinct reviews.
        d1 = client.get(f"/api/reviews/{rid1}").json()
        d2 = client.get(f"/api/reviews/{rid2}").json()
        assert d1["report_url"] != d2["report_url"]
        assert d1["report_url"].endswith(f"{rid1}/report/file")
        assert d2["report_url"].endswith(f"{rid2}/report/file")
