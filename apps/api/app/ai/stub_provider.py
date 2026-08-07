"""Offline provider (no LLM).

Used when no AI key is configured. Extraction uses OCR text + the generic parser.
The advisory is a *deterministic, data-grounded* narrative composed from the actual
extracted fields and rule-engine findings — it never fabricates, and it is clearly
labelled as non-LLM. Configuring an API key upgrades this to full consultant-style
LLM analysis.
"""

from __future__ import annotations

from ..services.field_extraction import missing_fields, parse_invoice
from ..vat.schemas import Invoice, ReviewResult
from .base import AdvisoryResult, ChatMessage, ExtractionInput


def _fmt(value) -> str:
    return "—" if value in (None, "") else str(value)


def _deterministic_narrative(invoice: Invoice, review: ReviewResult) -> str:
    inv_no = _fmt(invoice.invoice_number)
    supplier = _fmt(invoice.supplier.name) if invoice.supplier else "—"
    recipient = _fmt(invoice.recipient.name) if invoice.recipient else "—"
    cur = _fmt(invoice.currency)
    lines: list[str] = []
    lines.append(
        f"This is a {invoice.invoice_type.value.replace('_', ' ')} "
        f"(no. {inv_no}) from {supplier} to {recipient}. "
        f"The deterministic rule engine assessed it as "
        f"{review.compliance_status.value.upper()} with {review.risk_level.value.upper()} risk."
    )
    if invoice.total_gross is not None:
        lines.append(
            f"Recorded totals — net {_fmt(invoice.total_net)}, VAT {_fmt(invoice.total_vat)}, "
            f"gross {_fmt(invoice.total_gross)} {cur}. "
            f"The engine's recomputed VAT is {_fmt(review.recomputed_vat)}."
        )
    if review.findings:
        lines.append("Findings the engine raised (with the article each relies on):")
        for f in review.findings:
            ref = f" [{f.legal_ref}]" if f.legal_ref else ""
            lines.append(f"  • {f.severity.value.upper()}: {f.title} — {f.detail}{ref}")
    else:
        lines.append("No rule violations were found against the mandatory VAT particulars checked.")

    missing = missing_fields(invoice)
    if missing:
        lines.append(
            "Fields not confidently extracted (verify against the source document): "
            + ", ".join(missing)
            + "."
        )
    lines.append(
        "Note: this narrative is generated deterministically from the extracted data (no LLM). "
        "Configure an AI provider (AI_PROVIDER + API key) for consultant-style interpretation."
    )
    return "\n".join(lines)


class StubProvider:
    name = "stub"

    def extract_invoice(self, source: ExtractionInput) -> Invoice:
        """Offline extraction via OCR text + the generic, layout-agnostic parser."""
        return parse_invoice(source.text or "")

    def advise(
        self, invoice: Invoice, review: ReviewResult, source_text: str | None = None
    ) -> AdvisoryResult:
        return AdvisoryResult(
            narrative=_deterministic_narrative(invoice, review),
            recommendations=[f.recommendation for f in review.findings if f.recommendation],
            citations=sorted({f.legal_ref for f in review.findings if f.legal_ref}),
            confidence="n/a",
            provider=self.name,
            grounded=True,
            llm_used=False,
        )

    def chat(self, messages: list[ChatMessage], context: str | None = None) -> str:
        if context:
            # Extractive fallback: surface the retrieved FTA source material directly.
            return (
                "No generative AI provider is configured, so here is the most relevant "
                "retrieved FTA source material for your question. Configure an API key for "
                "a synthesised consultant-style answer.\n\n" + context
            )
        return (
            "AI assistant is not configured, and no matching knowledge-base content was "
            "found. Seed the knowledge base (POST /api/knowledge/seed) and/or set "
            "AI_PROVIDER + an API key to enable grounded VAT advice."
        )
