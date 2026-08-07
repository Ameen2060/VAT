"""Tests for the AI integration: status reporting, data-grounded offline advisory,
provider auto-detection, and the LLM advise plumbing (with a mocked client)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.ai.factory import _resolve_provider_name
from app.ai.stub_provider import StubProvider
from app.main import app
from app.vat.rules import review_invoice
from app.vat.schemas import Invoice, InvoiceType, PartyDetails, TransactionType, VatTreatment


def _invoice() -> Invoice:
    return Invoice(
        invoice_type=InvoiceType.TAX_INVOICE,
        invoice_number="CMECLLC20260701",
        invoice_date="2026-07-09",
        supplier=PartyDetails(name="CITIC MIDDLE EAST", address="Dubai", trn="105110997100003"),
        recipient=PartyDetails(name="MAG PARK", address="Dubai", trn="104215659400003"),
        transaction_type=TransactionType.LOCAL,
        treatment=VatTreatment.STANDARD,
        currency="AED",
        total_net=Decimal("33750000.00"),
        total_vat=Decimal("1687500.00"),
        total_gross=Decimal("35437500.00"),
        has_tax_invoice_label=True,
    )


# ── offline advisory is data-grounded, not a dead-end ────────────────────────
def test_stub_advisory_references_real_data():
    inv = _invoice()
    result = review_invoice(inv)
    adv = StubProvider().advise(inv, result, source_text="TAX INVOICE ... TRN:105110997100003")
    assert "unavailable" not in adv.narrative.lower()
    assert "CMECLLC20260701" in adv.narrative          # references the actual invoice number
    assert adv.llm_used is False
    assert result.compliance_status.value.upper() in adv.narrative.upper()


# ── provider auto-detection from keys ────────────────────────────────────────
def test_resolve_provider_prefers_explicit_then_infers():
    assert _resolve_provider_name(SimpleNamespace(ai_provider="anthropic", anthropic_api_key="x", openai_api_key="")) == "anthropic"
    # unset provider but a key present → inferred
    assert _resolve_provider_name(SimpleNamespace(ai_provider="", anthropic_api_key="k", openai_api_key="")) == "anthropic"
    assert _resolve_provider_name(SimpleNamespace(ai_provider="none", anthropic_api_key="", openai_api_key="k")) == "openai"
    assert _resolve_provider_name(SimpleNamespace(ai_provider="", anthropic_api_key="", openai_api_key="")) == "none"


# ── status endpoint reports unconfigured clearly ─────────────────────────────
def test_ai_status_unconfigured():
    with TestClient(app) as client:
        s = client.get("/api/ai/status").json()
        assert s["configured"] is False
        assert s["ready"] is False
        assert "AI_PROVIDER" in s["message"]


# ── Anthropic advise plumbing, mocked (no SDK/key needed) ────────────────────
class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeMessages:
    def __init__(self, capture):
        self._capture = capture

    def create(self, **kwargs):
        self._capture["messages"] = kwargs.get("messages")
        return SimpleNamespace(
            content=[
                _FakeBlock(
                    '{"narrative": "Invoice CMECLLC20260701 from CITIC to MAG is compliant.",'
                    ' "recommendations": ["Retain the tax invoice"],'
                    ' "citations": ["Art. 59(1) ER"], "confidence": "high"}'
                )
            ]
        )


def _mock_anthropic_provider(capture):
    from app.ai.anthropic_provider import AnthropicProvider

    p = AnthropicProvider.__new__(AnthropicProvider)  # bypass __init__ (no real key/SDK)
    p._client = SimpleNamespace(messages=_FakeMessages(capture))
    p._model = "claude-sonnet-5"
    p._max_tokens = 1024
    return p


def test_anthropic_advise_is_grounded_and_parsed():
    capture: dict = {}
    provider = _mock_anthropic_provider(capture)
    inv = _invoice()
    result = review_invoice(inv)

    adv = provider.advise(inv, result, source_text="RAW OCR: TRN:105110997100003 Total 35,437,500.00")

    # The prompt sent to the model must contain the real extracted data (grounding).
    sent = capture["messages"][0]["content"]
    assert "CMECLLC20260701" in sent
    assert "35437500.00" in sent or "35,437,500.00" in sent
    assert "RAW OCR" in sent  # raw source text was included

    # The JSON reply is parsed and flagged as LLM-produced.
    assert adv.llm_used is True
    assert adv.provider == "anthropic"
    assert "CMECLLC20260701" in adv.narrative
    assert adv.confidence == "high"


def test_anthropic_advise_falls_back_on_error():
    from app.ai.anthropic_provider import AnthropicProvider

    class _Boom:
        def create(self, **kwargs):
            raise RuntimeError("401 authentication_error: invalid x-api-key")

    p = AnthropicProvider.__new__(AnthropicProvider)
    p._client = SimpleNamespace(messages=_Boom())
    p._model = "claude-sonnet-5"
    p._max_tokens = 1024

    inv = _invoice()
    adv = p.advise(inv, review_invoice(inv))
    assert adv.llm_used is False
    assert adv.error is not None
    assert "Authentication" in adv.error
    # Still returns a useful deterministic narrative rather than crashing.
    assert "CMECLLC20260701" in adv.narrative
