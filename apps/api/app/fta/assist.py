"""FTA-grounded VAT Assistant reasoning.

Turns a user question into an FTA-anchored answer scaffold: identifies the VAT issue,
resolves the applicable rule *as of* the relevant date (never superseded/outdated),
gathers official source references + effective dates, and determines whether the
conclusion is grounded or must be flagged Provisional (SME validation required).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FtaUpdate, VatRuleVersion
from .service import rule_as_of

PROVISIONAL_NOTE = "Provisional — UAE VAT SME validation required before filing."

# Source-authority hierarchy (requirement: distinguish these tiers).
HIERARCHY = [
    "Official FTA Requirement",
    "Official FTA Guidance",
    "System Rule",
    "SME Interpretation",
    "Provisional Recommendation",
]

# VAT issue topics -> keywords + backing rule keys + canonical treatment label.
TOPICS: list[dict] = [
    {"name": "Standard-rated supply", "treatment": "Standard-rated (5%)",
     "keys": ["standard_rate"], "kw": ["standard rate", "standard-rated", "5%", "output vat"]},
    {"name": "Zero-rated supply / Export", "treatment": "Zero-rated (0%)",
     "keys": ["zero_rated_supplies"],
     "kw": ["zero rated", "zero-rated", "0%", "export", "exports", "international transport"]},
    {"name": "Exempt supply", "treatment": "Exempt (no VAT, no input recovery)",
     "keys": ["exempt_supplies"],
     "kw": ["exempt", "financial service", "bare land", "residential", "local passenger transport"]},
    {"name": "Reverse charge", "treatment": "Reverse charge (self-account output + input)",
     "keys": ["reverse_charge"],
     "kw": ["reverse charge", "rcm", "import of service", "imported service", "concerned services"]},
    {"name": "Import of goods", "treatment": "Import VAT (reverse charge / customs)",
     "keys": ["reverse_charge"], "kw": ["import of goods", "imports", "customs", "import vat"]},
    {"name": "VAT registration", "treatment": "Registration thresholds",
     "keys": ["registration_threshold_mandatory", "registration_threshold_voluntary"],
     "kw": ["register", "registration", "threshold", "375,000", "187,500"]},
    {"name": "VAT deregistration", "treatment": "Deregistration rules",
     "keys": ["registration_threshold_mandatory"], "kw": ["deregister", "deregistration"]},
    {"name": "Input VAT recovery", "treatment": "Input VAT recovery / blocked items",
     "keys": ["input_recovery"],
     "kw": ["input vat", "recover", "recovery", "blocked", "entertainment", "motor vehicle"]},
    {"name": "VAT return / filing", "treatment": "Return filing & payment",
     "keys": ["return_filing"],
     "kw": ["return", "vat201", "filing", "file", "deadline", "28 days", "tax period"]},
    {"name": "VAT refund", "treatment": "Refund of excess input VAT",
     "keys": ["return_filing"], "kw": ["refund", "vat311", "excess"]},
    {"name": "Designated Zone", "treatment": "Designated Zone treatment",
     "keys": ["designated_zones"], "kw": ["designated zone", "free zone", "freezone"]},
    {"name": "Credit / Debit notes", "treatment": "Adjustment via tax credit/debit note",
     "keys": ["standard_rate"], "kw": ["credit note", "debit note", "adjustment"]},
    {"name": "Tax invoice", "treatment": "Tax invoice requirements",
     "keys": ["standard_rate"], "kw": ["tax invoice", "invoice requirement", "mandatory fields"]},
    {"name": "Advances / Retention", "treatment": "Tax point on advances & retention",
     "keys": ["standard_rate"], "kw": ["advance", "advances", "retention", "date of supply", "tax point"]},
    {"name": "Penalties & compliance", "treatment": "Administrative penalties",
     "keys": [], "kw": ["penalty", "penalties", "fine", "non-compliance", "late"]},
    {"name": "Out-of-scope", "treatment": "Out of scope of UAE VAT",
     "keys": [], "kw": ["out of scope", "out-of-scope", "outside the scope"]},
]


def _match_topics(query: str) -> list[dict]:
    q = query.lower()
    matched = [t for t in TOPICS if any(k in q for k in t["kw"])]
    return matched


def resolve_context(db: Session, query: str, on: str | None = None) -> dict:
    """Build FTA-grounded context + metadata for a question.

    Returns: context (str for the LLM), citations (list), sources (structured),
    vat_issue, applicable_treatment, effective_date, publication_date, rule_reference,
    validation_status ("grounded" | "provisional" | "requires_sme").
    """
    on = on or date.today().isoformat()
    topics = _match_topics(query)

    sources: list[dict] = []
    citations: list[str] = []
    rule_keys: list[str] = []
    requires_validation = False
    primary_effective: str | None = None

    for t in topics:
        for key in t["keys"]:
            rule = rule_as_of(db, key, on)
            if not rule:
                continue
            # Superseded or SME-gated (unapproved) rules must not ground the answer.
            if rule.status == "superseded":
                continue
            if rule.requires_validation:
                requires_validation = True
                continue
            rule_keys.append(rule.rule_key)
            primary_effective = primary_effective or rule.effective_from
            sources.append({
                "tier": "Official FTA Requirement",
                "title": rule.title,
                "value": rule.value,
                "source_ref": rule.source_ref,
                "effective_from": rule.effective_from,
                "effective_to": rule.effective_to,
            })
            citations.append(f"{rule.source_ref} (eff. {rule.effective_from})")

    # Approved/implemented regulatory updates relevant to the matched treatments.
    approved = db.execute(
        select(FtaUpdate).where(FtaUpdate.status.in_(["approved", "implemented"]))
        .order_by(FtaUpdate.effective_date.desc())
    ).scalars()
    ql = query.lower()
    for u in approved:
        hay = f"{u.title} {u.affected_treatment or ''} {u.affected_module or ''}".lower()
        if any(t["name"].split()[0].lower() in hay for t in topics) or any(
            k in hay for t in topics for k in t["kw"]
        ):
            tier = "Official FTA Requirement" if u.classification == "legally_effective" else "Official FTA Guidance"
            sources.append({
                "tier": tier, "title": u.title, "value": u.new_rule,
                "source_ref": u.source_ref, "effective_from": u.effective_date,
                "effective_to": None,
            })
            if u.source_ref:
                citations.append(f"{u.source_ref} (FTA update, eff. {u.effective_date or 'n/a'})")

    vat_issue = topics[0]["name"] if topics else "General VAT enquiry"
    treatment = topics[0]["treatment"] if topics else None

    if not topics or (requires_validation and not sources):
        validation_status = "requires_sme"
    elif requires_validation:
        validation_status = "provisional"
    elif sources:
        validation_status = "grounded"
    else:
        validation_status = "requires_sme"

    # Build the grounding context for the model, prioritising official FTA sources.
    lines = [
        "You are a UAE VAT senior consultant. Answer using ONLY the authoritative UAE FTA "
        "basis below (prioritise official FTA sources over anything else). Structure the answer:",
        "1) VAT issue identified  2) Applicable VAT treatment  3) Reasoning  "
        "4) Official FTA source/reference  5) Effective date  6) Whether SME validation is required.",
        "Never present an unvalidated interpretation as confirmed UAE FTA filing advice.",
        "",
        f"Detected VAT issue: {vat_issue}",
        f"Indicated treatment: {treatment or 'to be determined'}",
        f"Applicable as of: {on}",
        "",
        "Authoritative UAE FTA basis:",
    ]
    if sources:
        for s in sources:
            eff = s["effective_from"] or "n/a"
            lines.append(f"- [{s['tier']}] {s['title']}: {s['value']}. "
                         f"Source: {s['source_ref']}. Effective from {eff}.")
    else:
        lines.append("- (No confidently matching official FTA rule was found for this query.)")
    if validation_status != "grounded":
        lines.append("")
        lines.append(f"IMPORTANT: End the answer with: \"{PROVISIONAL_NOTE}\"")

    return {
        "context": "\n".join(lines),
        "citations": list(dict.fromkeys(citations)),  # de-dup, keep order
        "sources": sources,
        "vat_issue": vat_issue,
        "applicable_treatment": treatment,
        "rule_reference": ", ".join(dict.fromkeys(rule_keys)) or None,
        "effective_date": primary_effective,
        "validation_status": validation_status,
    }
