"""AI status, verification, and analysis endpoints.

The AI layer interprets the deterministic engine's output; it never replaces it.
These endpoints make AI configuration observable and let users (re)generate
data-grounded analysis for existing documents.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.factory import ai_status, verify_ai
from ..core.database import get_db
from ..models import Review
from ..services.review_service import combined_analysis, reanalyze_advisory

router = APIRouter(prefix="/api/ai", tags=["ai"])


class CombinedRequest(BaseModel):
    review_ids: list[str]


@router.get("/status")
def status() -> dict:
    """Current AI configuration (no network call)."""
    return ai_status()


@router.post("/verify")
def verify() -> dict:
    """Make a minimal live call to confirm the key/model actually work."""
    return verify_ai()


@router.post("/reviews/{review_id}/reanalyze")
def reanalyze(review_id: str, db: Session = Depends(get_db)) -> dict:
    """Regenerate the AI advisory for an existing review with the current provider."""
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    reanalyze_advisory(db, r)
    return {"id": r.id, "advisory": r.advisory_json}


@router.post("/analyze/combined")
def analyze_combined(body: CombinedRequest, db: Session = Depends(get_db)) -> dict:
    """Cross-document AI analysis over several reviews."""
    if not body.review_ids:
        raise HTTPException(status_code=400, detail="Provide at least one review_id.")
    reviews = [db.get(Review, rid) for rid in body.review_ids]
    reviews = [r for r in reviews if r is not None]
    if not reviews:
        raise HTTPException(status_code=404, detail="No matching reviews found.")
    return {"count": len(reviews), "analysis": combined_analysis(db, reviews)}
