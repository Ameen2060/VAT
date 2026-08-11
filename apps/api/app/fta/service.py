"""FTA update workflow, dashboard and effective-dated rule resolution."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FtaSource, FtaUpdate, VatRuleVersion

# NEW -> UNDER_REVIEW -> APPROVED -> IMPLEMENTED (+ REJECTED). Nothing hits the live
# engine before APPROVED (requirement #5).
STATUS_FLOW: dict[str, set[str]] = {
    "new": {"under_review", "rejected"},
    "under_review": {"approved", "rejected", "new"},
    "approved": {"implemented", "under_review"},
    "implemented": set(),
    "rejected": {"new"},
}


class TransitionError(ValueError):
    pass


def transition(db: Session, update: FtaUpdate, new_status: str, actor: str | None) -> FtaUpdate:
    """Move an update through the review workflow, enforcing allowed transitions."""
    current = update.status
    if new_status == current:
        return update
    allowed = STATUS_FLOW.get(current, set())
    if new_status not in allowed:
        raise TransitionError(
            f"Cannot move from '{current}' to '{new_status}'. Allowed: {sorted(allowed) or 'none'}."
        )
    update.status = new_status
    if new_status == "approved":
        update.approved_by = actor
    if new_status == "implemented":
        update.implemented_at = datetime.now(timezone.utc)
        # Requirement #8: validate the live engine after implementing.
        from .validation import run_compliance_validation

        update.validation_json = run_compliance_validation()
    db.commit()
    db.refresh(update)
    return update


def dashboard(db: Session) -> dict:
    """Counts + highlights for the dashboard FTA VAT Updates section (requirement #6)."""
    rows = db.execute(select(FtaUpdate.status, func.count()).group_by(FtaUpdate.status)).all()
    by_status = {s: n for s, n in rows}
    today = date.today().isoformat()

    upcoming = list(
        db.execute(
            select(FtaUpdate)
            .where(
                FtaUpdate.effective_date.is_not(None),
                FtaUpdate.effective_date >= today,
                FtaUpdate.status != "implemented",
            )
            .order_by(FtaUpdate.effective_date)
            .limit(10)
        ).scalars()
    )
    critical = list(
        db.execute(
            select(FtaUpdate)
            .where(FtaUpdate.critical.is_(True), FtaUpdate.status != "implemented")
            .order_by(FtaUpdate.created_at.desc())
            .limit(10)
        ).scalars()
    )
    modules = [
        m for (m,) in db.execute(
            select(FtaUpdate.affected_module).where(FtaUpdate.affected_module.is_not(None)).distinct()
        ).all()
    ]
    src = db.execute(select(FtaSource.last_status, func.count()).group_by(FtaSource.last_status)).all()

    return {
        "new": by_status.get("new", 0),
        "under_review": by_status.get("under_review", 0),
        "approved": by_status.get("approved", 0),
        "implemented": by_status.get("implemented", 0),
        "rejected": by_status.get("rejected", 0),
        "critical": db.scalar(
            select(func.count()).select_from(FtaUpdate).where(
                FtaUpdate.critical.is_(True), FtaUpdate.status != "implemented"
            )
        ) or 0,
        "total": db.scalar(select(func.count()).select_from(FtaUpdate)) or 0,
        "affected_modules": [m for m in modules if m],
        "upcoming_effective": [
            {"id": u.id, "title": u.title, "effective_date": u.effective_date,
             "status": u.status, "affected_module": u.affected_module, "critical": u.critical}
            for u in upcoming
        ],
        "critical_pending": [
            {"id": u.id, "title": u.title, "status": u.status, "effective_date": u.effective_date,
             "affected_module": u.affected_module}
            for u in critical
        ],
        "sources": {s: n for s, n in src},
    }


def rule_as_of(db: Session, rule_key: str, on: str | None = None) -> VatRuleVersion | None:
    """The rule version in force on a given date — historical protection (requirement #7)."""
    on = on or date.today().isoformat()
    candidates = db.execute(
        select(VatRuleVersion)
        .where(VatRuleVersion.rule_key == rule_key, VatRuleVersion.effective_from <= on)
        .order_by(VatRuleVersion.effective_from.desc())
    ).scalars()
    for v in candidates:
        if v.effective_to is None or v.effective_to >= on:
            return v
    return None
