"""OpenAI provider — parallel implementation to the Anthropic adapter.

Kept minimal; extraction uses the vision-capable chat completions API. The
`openai` package is imported lazily.
"""

from __future__ import annotations

import base64
import json

from ..vat.schemas import Invoice, ReviewResult
from .anthropic_provider import _strip_json
from .base import AdvisoryResult, ChatMessage, ExtractionInput
from .prompts import EXTRACTION_INSTRUCTION, VAT_CONSULTANT_SYSTEM, advisory_user_prompt


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        import openai  # lazy import

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self._client = openai.OpenAI(api_key=api_key)
        # Map Claude-style default to a sensible OpenAI model if needed.
        self._model = model if model.startswith("gpt") else "gpt-4o"
        self._max_tokens = max_tokens

    def _chat(self, system: str, user_content) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    def extract_invoice(self, source: ExtractionInput) -> Invoice:
        schema = json.dumps(Invoice.model_json_schema())
        parts: list = [{"type": "text", "text": f"{EXTRACTION_INSTRUCTION}\n\nSchema:\n{schema}"}]
        if source.text:
            parts.append({"type": "text", "text": f"Document text:\n{source.text}"})
        if source.doc_bytes and (source.mime or "").startswith("image/"):
            b64 = base64.standard_b64encode(source.doc_bytes).decode()
            parts.append(
                {"type": "image_url", "image_url": {"url": f"data:{source.mime};base64,{b64}"}}
            )
        raw = self._chat(VAT_CONSULTANT_SYSTEM, parts)
        try:
            return Invoice.model_validate_json(_strip_json(raw))
        except Exception:  # noqa: BLE001
            inv = Invoice()
            inv.notes = "AI extraction returned unparseable output; manual review required."
            return inv

    def advise(
        self, invoice: Invoice, review: ReviewResult, source_text: str | None = None
    ) -> AdvisoryResult:
        prompt = advisory_user_prompt(
            invoice.model_dump_json(indent=2), review.model_dump_json(indent=2), source_text
        )
        try:
            raw = self._chat(VAT_CONSULTANT_SYSTEM, prompt)
        except Exception as e:  # noqa: BLE001
            from .anthropic_provider import _describe_error
            from .stub_provider import StubProvider

            fallback = StubProvider().advise(invoice, review, source_text)
            fallback.error = _describe_error(e)
            return fallback
        try:
            data = json.loads(_strip_json(raw))
            return AdvisoryResult(
                narrative=data.get("narrative", "") or raw,
                recommendations=list(data.get("recommendations", [])),
                citations=list(data.get("citations", [])),
                confidence=data.get("confidence", "n/a"),
                provider=self.name,
                llm_used=True,
            )
        except Exception:  # noqa: BLE001
            return AdvisoryResult(narrative=raw, provider=self.name, llm_used=True)

    def combined_analysis(self, documents_block: str) -> AdvisoryResult:
        from .prompts import combined_analysis_prompt

        try:
            raw = self._chat(VAT_CONSULTANT_SYSTEM, combined_analysis_prompt(documents_block))
            data = json.loads(_strip_json(raw))
            return AdvisoryResult(
                narrative=data.get("narrative", "") or raw,
                recommendations=list(data.get("recommendations", [])),
                citations=list(data.get("citations", [])),
                confidence=data.get("confidence", "n/a"),
                provider=self.name,
                llm_used=True,
            )
        except Exception as e:  # noqa: BLE001
            from .anthropic_provider import _describe_error

            return AdvisoryResult(narrative="", provider=self.name, error=_describe_error(e))

    def verify(self) -> None:
        self._client.chat.completions.create(
            model=self._model, max_tokens=8, messages=[{"role": "user", "content": "ping"}]
        )

    def chat(self, messages: list[ChatMessage], context: str | None = None) -> str:
        system = VAT_CONSULTANT_SYSTEM
        if context:
            system += "\n\nUse ONLY the following retrieved FTA material:\n\n" + context
        payload = [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content} for m in messages
        ]
        resp = self._client.chat.completions.create(
            model=self._model, max_tokens=self._max_tokens, messages=payload
        )
        return (resp.choices[0].message.content or "").strip()
