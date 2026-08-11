"""VAT AI Assistant API.

Natural-language Q&A through the configured AI provider using the senior-consultant
persona, grounded in the FTA knowledge base (RAG). Users can also attach a document
(PDF / Word / image); its extracted text becomes additional grounding for the chat.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.base import ChatMessage
from ..ai.factory import get_ai_provider
from ..auth.deps import get_current_user
from ..core.database import get_db
from ..fta import assist
from ..models import AssistantAudit, User
from ..rag.store import build_context, retrieve
from ..services import archive as archive_svc
from ..services import extraction

router = APIRouter(prefix="/api", tags=["assistant"])

# Formats a user may attach to the assistant.
ASSISTANT_UPLOAD_EXT = (".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png")
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024      # 15 MB
_MAX_CONTEXT_CHARS = 20_000               # cap the text fed into the chat context


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatTurn]
    # Optional attached-document grounding (from /api/assistant/upload).
    document_name: str | None = None
    document_text: str | None = None
    # Optional transaction/tax-period date so the answer uses the rule in force then.
    as_of_date: str | None = None


class FtaSourceRef(BaseModel):
    tier: str
    title: str
    source_ref: str | None = None
    effective_from: str | None = None


class ChatResponse(BaseModel):
    reply: str
    provider: str
    citations: list[str] = []
    grounded: bool = False
    # FTA-grounded analysis metadata.
    vat_issue: str | None = None
    applicable_treatment: str | None = None
    effective_date: str | None = None
    validation_status: str = "grounded"   # grounded | provisional | requires_sme
    provisional: bool = False
    fta_sources: list[FtaSourceRef] = []
    audit_id: str | None = None


class AssistantUploadResponse(BaseModel):
    filename: str
    text: str
    chars: int
    ocr_used: bool = False
    truncated: bool = False
    warnings: list[str] = []


@router.post("/assistant/upload", response_model=AssistantUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantUploadResponse:
    """Extract text from an attached document so the assistant can answer about it.

    Accepts PDF, Word (.docx/.doc) and images (.jpg/.jpeg/.png). Images and scanned
    PDFs are run through OCR. The extracted text is returned to the client, which
    passes it back on the next chat turn as grounding.
    """
    name = file.filename or "document"
    lower = name.lower()
    if not lower.endswith(ASSISTANT_UPLOAD_EXT):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PDF, Word (.docx/.doc), JPG/JPEG or PNG.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15 MB).")

    # Archive the attached document so it stays available for future review/download.
    archive_svc.archive_file(
        db, filename=name, data=data, mime=file.content_type,
        source=archive_svc.SOURCE_ASSISTANT, uploaded_by=getattr(user, "email", None),
    )

    try:
        te = extraction._read_text(name, data)
    except extraction.UnsupportedFileError as e:
        raise HTTPException(status_code=415, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 — surface extraction failures cleanly
        raise HTTPException(status_code=422, detail=f"Could not read the document: {e}") from e

    text = (te.text or "").strip()
    warnings = list(te.warnings)
    if not text:
        warnings.append(
            "No readable text could be extracted from this document. "
            "If it's a legacy .doc or a low-quality scan, try uploading a PDF."
        )
    truncated = len(text) > _MAX_CONTEXT_CHARS
    if truncated:
        text = text[:_MAX_CONTEXT_CHARS]
        warnings.append(f"Only the first {_MAX_CONTEXT_CHARS:,} characters are used as context.")

    return AssistantUploadResponse(
        filename=name,
        text=text,
        chars=len(text),
        ocr_used=te.ocr_used,
        truncated=truncated,
        warnings=warnings,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatResponse:
    provider = get_ai_provider()
    history = [ChatMessage(role=m.role, content=m.content) for m in req.messages]

    last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    citations: list[str] = []
    parts: list[str] = []

    # 1) FTA-grounded basis FIRST (official sources take priority over everything else).
    fta = assist.resolve_context(db, last_user, req.as_of_date) if last_user else None
    if fta:
        parts.append(fta["context"])
        citations.extend(fta["citations"])

    # 2) Attached-document text, if any.
    if req.document_text and req.document_text.strip():
        label = req.document_name or "the attached document"
        parts.append(
            f'The user attached a document ("{label}"). Use its content to answer '
            f'their questions:\n"""\n{req.document_text.strip()}\n"""'
        )

    # 3) RAG over the FTA knowledge base (supplementary).
    if last_user:
        hits = retrieve(db, last_user, k=5)
        if hits:
            rag_context, rag_cites = build_context(hits)
            parts.append(rag_context)
            citations.extend(rag_cites)

    context = "\n\n".join(parts) if parts else None
    reply = provider.chat(history, context=context)

    validation_status = fta["validation_status"] if fta else "requires_sme"
    provisional = validation_status != "grounded"
    # Ensure the provisional disclaimer is present when required (belt-and-braces vs the LLM).
    if provisional and assist.PROVISIONAL_NOTE not in reply:
        reply = f"{reply}\n\n⚠️ {assist.PROVISIONAL_NOTE}"

    citations = list(dict.fromkeys(citations))
    sources = [
        FtaSourceRef(tier=s["tier"], title=s["title"], source_ref=s.get("source_ref"),
                    effective_from=s.get("effective_from"))
        for s in (fta["sources"] if fta else [])
    ]

    # Audit trail: store the recommendation with its FTA basis + validation status.
    audit = AssistantAudit(
        question=last_user[:4000],
        vat_issue=fta["vat_issue"] if fta else None,
        applicable_treatment=fta["applicable_treatment"] if fta else None,
        rule_reference=fta["rule_reference"] if fta else None,
        fta_source="; ".join(citations)[:4000] or None,
        effective_date=fta["effective_date"] if fta else None,
        response=reply[:8000],
        validation_status=validation_status,
        user_email=getattr(user, "email", None),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    return ChatResponse(
        reply=reply,
        provider=getattr(provider, "name", "unknown"),
        citations=citations,
        grounded=bool(citations) or bool(req.document_text),
        vat_issue=fta["vat_issue"] if fta else None,
        applicable_treatment=fta["applicable_treatment"] if fta else None,
        effective_date=fta["effective_date"] if fta else None,
        validation_status=validation_status,
        provisional=provisional,
        fta_sources=sources,
        audit_id=audit.id,
    )


class AuditOut(BaseModel):
    id: str
    question: str
    vat_issue: str | None
    applicable_treatment: str | None
    rule_reference: str | None
    fta_source: str | None
    effective_date: str | None
    validation_status: str
    user_email: str | None
    created_at: str | None


@router.get("/assistant/audit", response_model=list[AuditOut])
def list_audit(limit: int = 100, db: Session = Depends(get_db)) -> list[AuditOut]:
    """The VAT Assistance audit trail — every recommendation with its FTA basis."""
    from sqlalchemy import select

    rows = db.execute(
        select(AssistantAudit).order_by(AssistantAudit.created_at.desc()).limit(min(limit, 500))
    ).scalars()
    return [
        AuditOut(
            id=a.id, question=a.question, vat_issue=a.vat_issue,
            applicable_treatment=a.applicable_treatment, rule_reference=a.rule_reference,
            fta_source=a.fta_source, effective_date=a.effective_date,
            validation_status=a.validation_status, user_email=a.user_email,
            created_at=a.created_at.isoformat() if a.created_at else None,
        )
        for a in rows
    ]
