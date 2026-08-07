"""AI provider interface and shared data types."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..vat.schemas import Invoice, ReviewResult


class ExtractionInput(BaseModel):
    """Everything the AI needs to extract a structured invoice from a document."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    filename: str
    mime: str | None = None
    text: str | None = None          # pre-extracted text (e.g. from a text PDF)
    doc_bytes: bytes | None = None   # raw bytes for vision/document input (scans, images)


class AdvisoryResult(BaseModel):
    """The AI VAT consultant's narrative layered on top of the rule engine."""

    narrative: str = ""
    recommendations: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: str = "n/a"          # low | medium | high | n/a
    provider: str = "none"
    grounded: bool = True            # False if the model answered without retrieval/rules
    llm_used: bool = False           # True only when a real LLM produced the narrative
    error: str | None = None         # populated if the AI call failed / fell back


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


@runtime_checkable
class AIProvider(Protocol):
    """Contract every AI backend implements. Swappable via configuration."""

    name: str

    def extract_invoice(self, source: ExtractionInput) -> Invoice:
        """Turn a document/image into a normalised :class:`Invoice`."""
        ...

    def advise(
        self, invoice: Invoice, review: ReviewResult, source_text: str | None = None
    ) -> AdvisoryResult:
        """Produce a senior-consultant advisory that explains the rule findings,
        grounded in the structured invoice, the rule verdict and the raw source text."""
        ...

    def chat(self, messages: list[ChatMessage], context: str | None = None) -> str:
        """Answer a VAT question, grounded in the provided context (RAG in Phase 2)."""
        ...
