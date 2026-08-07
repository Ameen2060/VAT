"""VAT AI Assistant API.

Phase 2 (this slice): natural-language Q&A through the configured AI provider using
the senior-consultant persona. RAG grounding over the FTA knowledge base is layered
in next — the endpoint contract stays the same, gaining a `citations` field.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.base import ChatMessage
from ..ai.factory import get_ai_provider
from ..core.database import get_db
from ..rag.store import build_context, retrieve

router = APIRouter(prefix="/api", tags=["assistant"])


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatTurn]


class ChatResponse(BaseModel):
    reply: str
    provider: str
    citations: list[str] = []
    grounded: bool = False


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    provider = get_ai_provider()
    history = [ChatMessage(role=m.role, content=m.content) for m in req.messages]

    # RAG: retrieve grounding for the latest user turn.
    last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    citations: list[str] = []
    context: str | None = None
    if last_user:
        hits = retrieve(db, last_user, k=5)
        if hits:
            context, citations = build_context(hits)

    reply = provider.chat(history, context=context)
    return ChatResponse(
        reply=reply,
        provider=getattr(provider, "name", "unknown"),
        citations=citations,
        grounded=bool(citations),
    )
