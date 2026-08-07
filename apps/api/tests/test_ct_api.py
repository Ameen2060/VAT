"""API tests for the Corporate Tax module (Phase B): create/list/get/validate/compute/
dashboard/status over the persisted CT return."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _clean_payload() -> dict:
    return {
        "entity_name": "ACME Trading LLC",
        "trn": "100123456700003",
        "taxpayer_type": "resident_juridical",
        "is_ct_registered": True,
        "tax_period_start": "2024-01-01",
        "tax_period_end": "2024-12-31",
        "filing_date": "2025-06-30",
        "revenue": "2000000",
        "accounting_net_profit": "500000",
        "taxable_income": "500000",
        "corporate_tax_payable": "11250",
        "has_audited_financials": True,
    }


def test_create_and_get_ct_return():
    with TestClient(app) as client:
        r = client.post("/api/ct/returns", json=_clean_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        rid = body["id"]
        assert body["status"] == "draft"
        assert body["result"]["compliance_status"] == "pass"
        assert body["result"]["computed_tax"] == "11250.00"
        # computation trace is attached
        assert body["result"]["computation"]["ct_payable"] == "11250.00"

        got = client.get(f"/api/ct/returns/{rid}")
        assert got.status_code == 200
        assert got.json()["return"]["entity_name"] == "ACME Trading LLC"


def test_create_failing_return_and_list_filter():
    with TestClient(app) as client:
        bad = _clean_payload()
        bad["is_ct_registered"] = False  # CT-REG-001 → FAIL / high risk
        r = client.post("/api/ct/returns", json=bad)
        assert r.status_code == 200
        assert r.json()["result"]["compliance_status"] == "fail"

        # List filtered by high risk returns the failing one.
        lst = client.get("/api/ct/returns", params={"risk": "high"})
        assert lst.status_code == 200
        assert any(row["risk_level"] == "high" for row in lst.json())


def test_validate_and_compute_endpoints():
    with TestClient(app) as client:
        rid = client.post("/api/ct/returns", json=_clean_payload()).json()["id"]

        v = client.post(f"/api/ct/returns/{rid}/validate")
        assert v.status_code == 200
        assert v.json()["result"]["computed_tax"] == "11250.00"

        c = client.post(f"/api/ct/returns/{rid}/compute")
        assert c.status_code == 200
        comp = c.json()
        assert comp["taxable_income"] == "500000.00"
        assert comp["ct_payable"] == "11250.00"
        assert any(line["step"] == "ct_payable" for line in comp["lines"])


def test_patch_updates_and_reruns():
    with TestClient(app) as client:
        rid = client.post("/api/ct/returns", json=_clean_payload()).json()["id"]
        updated = _clean_payload()
        updated["corporate_tax_payable"] = "45000"  # wrong → CT-RATE-001
        p = client.patch(f"/api/ct/returns/{rid}", json=updated)
        assert p.status_code == 200
        ids = {f["rule_id"] for f in p.json()["result"]["findings"]}
        assert "CT-RATE-001" in ids
        assert p.json()["result"]["compliance_status"] == "fail"


def test_status_transition_and_validation():
    with TestClient(app) as client:
        rid = client.post("/api/ct/returns", json=_clean_payload()).json()["id"]
        ok = client.patch(f"/api/ct/returns/{rid}/status", json={"status": "tax_review"})
        assert ok.status_code == 200
        assert ok.json()["status"] == "tax_review"

        bad = client.patch(f"/api/ct/returns/{rid}/status", json={"status": "nonsense"})
        assert bad.status_code == 400


def test_dashboard_aggregates():
    with TestClient(app) as client:
        client.post("/api/ct/returns", json=_clean_payload())
        d = client.get("/api/ct/dashboard")
        assert d.status_code == 200
        body = d.json()
        assert body["total_returns"] >= 1
        assert "by_risk" in body and "by_status" in body
        assert "upcoming_deadlines" in body
