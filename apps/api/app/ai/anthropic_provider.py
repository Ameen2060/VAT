"""Anthropic (Claude) provider.

Handles structured invoice extraction (including OCR of scanned PDFs/images via
Claude's native document & vision input) and the VAT advisory narrative.

The `anthropic` package is imported lazily so the rest of the app runs without it.
"""

from __future__ import annotations

import base64
import json

from ..vat.schemas import Invoice, ReviewResult
from .base import AdvisoryResult, ChatMessage, ExtractionInput
from .prompts import EXTRACTION_INSTRUCTION, VAT_CONSULTANT_SYSTEM, advisory_user_prompt


def _describe_error(e: Exception) -> str:
    """Turn an SDK exception into a clear, actionable message for the UI/logs."""
    name = type(e).__name__
    msg = str(e)
    low = (name + " " + msg).lower()
    if "authentication" in low or "401" in low or "invalid x-api-key" in low or "api_key" in low:
        return "Authentication failed — the API key is missing or invalid."
    if "permission" in low or "403" in low:
        return "Permission denied for this API key or model."
    if "rate limit" in low or "429" in low:
        return "Rate limited by the provider — retry shortly."
    if "not_found" in low or "model" in low and "404" in low:
        return "The configured AI model was not found — check AI_MODEL."
    if "connection" in low or "timeout" in low or "network" in low:
        return "Could not reach the AI provider (network/connection error)."
    return f"AI provider error ({name}): {msg[:200]}"


def _strip_json(raw: str) -> str:
    """Extract the JSON object from a model response that may include prose/fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        import anthropic  # lazy import

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    # ── internals ────────────────────────────────────────────────────────────
    def _message(self, system: str, content: list | str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip()

    @staticmethod
    def _doc_block(source: ExtractionInput) -> dict | None:
        if not source.doc_bytes:
            return None
        b64 = base64.standard_b64encode(source.doc_bytes).decode()
        mime = source.mime or ""
        if mime == "application/pdf" or source.filename.lower().endswith(".pdf"):
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
            }
        if mime.startswith("image/") or source.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".gif")
        ):
            media = mime if mime.startswith("image/") else "image/png"
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": media, "data": b64},
            }
        return None

    # ── interface ────────────────────────────────────────────────────────────
    def extract_invoice(self, source: ExtractionInput) -> Invoice:
        schema = json.dumps(Invoice.model_json_schema())
        content: list = []
        block = self._doc_block(source)
        if block:
            content.append(block)
        if source.text:
            content.append({"type": "text", "text": f"Document text:\n{source.text}"})
        content.append(
            {"type": "text", "text": f"{EXTRACTION_INSTRUCTION}\n\nJSON schema:\n{schema}"}
        )

        raw = self._message(system=VAT_CONSULTANT_SYSTEM, content=content)
        try:
            return Invoice.model_validate_json(_strip_json(raw))
        except Exception:  # noqa: BLE001 — never crash the pipeline on a parse miss
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
            raw = self._message(system=VAT_CONSULTANT_SYSTEM, content=prompt)
        except Exception as e:  # noqa: BLE001 — surface the failure, keep the pipeline alive
            from .stub_provider import StubProvider

            fallback = StubProvider().advise(invoice, review, source_text)
            fallback.error = _describe_error(e)
            return fallback

        try:
            data = json.loads(_strip_json(raw))
            narrative = data.get("narrative", "") or raw
            return AdvisoryResult(
                narrative=narrative,
                recommendations=list(data.get("recommendations", [])),
                citations=list(data.get("citations", [])),
                confidence=data.get("confidence", "n/a"),
                provider=self.name,
                grounded=True,
                llm_used=True,
            )
        except Exception:  # noqa: BLE001 — non-JSON reply: keep the prose
            return AdvisoryResult(
                narrative=raw, provider=self.name, grounded=True, llm_used=True
            )

    def combined_analysis(self, documents_block: str) -> AdvisoryResult:
        from .prompts import combined_analysis_prompt

        try:
            raw = self._message(
                system=VAT_CONSULTANT_SYSTEM, content=combined_analysis_prompt(documents_block)
            )
            data = json.loads(_strip_json(raw))
            return AdvisoryResult(
                narrative=data.get("narrative", "") or raw,
                recommendations=list(data.get("recommendations", [])),
                citations=list(data.get("citations", [])),
                confidence=data.get("confidence", "n/a"),
                provider=self.name,
                grounded=True,
                llm_used=True,
            )
        except Exception as e:  # noqa: BLE001
            return AdvisoryResult(
                narrative="", provider=self.name, error=_describe_error(e), llm_used=False
            )

    def verify(self) -> None:
        """Make a minimal live call to confirm the key/model work. Raises on failure."""
        self._client.messages.create(
            model=self._model,
            max_tokens=8,
            messages=[{"role": "user", "content": "ping"}],
        )

    def chat(self, messages: list[ChatMessage], context: str | None = None) -> str:
        system = VAT_CONSULTANT_SYSTEM
        if context:
            system += (
                "\n\nUse ONLY the following retrieved FTA source material to answer. If it "
                "does not contain the answer, say so.\n\n" + context
            )
        payload = [{"role": m.role, "content": m.content} for m in messages]
        resp = self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens, system=system, messages=payload
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip()
