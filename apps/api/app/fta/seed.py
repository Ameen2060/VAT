"""Seed official monitored sources and the baseline effective-dated VAT rule registry.

Sources are the *official* UAE FTA / Ministry of Finance / Government portals only
(requirement #1). Baseline rules carry real legal citations and effective dates so the
system starts with full source traceability (requirement #9).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FtaSource, VatRuleVersion

# ── Official sources (primary legal sources only) ─────────────────────────────
SEED_SOURCES: list[dict] = [
    {"name": "FTA — VAT Legislation", "authority": "FTA", "category": "legislation",
     "url": "https://tax.gov.ae/en/legislation/"},
    {"name": "FTA — Public Clarifications", "authority": "FTA", "category": "clarification",
     "url": "https://tax.gov.ae/en/legislation/public.clarifications.aspx"},
    {"name": "FTA — VAT Guides & References", "authority": "FTA", "category": "guide",
     "url": "https://tax.gov.ae/en/guides.references/"},
    {"name": "FTA — Cabinet & FTA Decisions", "authority": "FTA", "category": "legislation",
     "url": "https://tax.gov.ae/en/legislation/cabinet.decisions.aspx"},
    {"name": "FTA — VAT (rates, registration, returns, refunds)", "authority": "FTA",
     "category": "procedures", "url": "https://tax.gov.ae/en/taxes/vat/"},
    {"name": "Ministry of Finance — Taxation", "authority": "MoF", "category": "legislation",
     "url": "https://mof.gov.ae/taxation/"},
    {"name": "UAE Legislation Portal", "authority": "Gov", "category": "legislation",
     "url": "https://uaelegislation.gov.ae/en"},
]

# ── Baseline VAT rules (effective-dated, cited) ───────────────────────────────
_DL8 = "Federal Decree-Law No. 8 of 2017 on VAT"
_ER = "Cabinet Decision No. 52 of 2017 (Executive Regulation of the VAT Law)"

SEED_RULES: list[dict] = [
    {"rule_key": "standard_rate", "title": "Standard VAT rate", "category": "rate",
     "value": "5%", "effective_from": "2018-01-01",
     "source_ref": f"{_DL8}, Article 3"},
    {"rule_key": "zero_rated_supplies", "title": "Zero-rated supplies (0%)", "category": "treatment",
     "value": "Exports of goods/services outside GCC implementing states; international transport; "
              "investment precious metals; new residential (first supply, 3 yrs); certain "
              "education & healthcare.",
     "effective_from": "2018-01-01", "source_ref": f"{_DL8}, Article 45; {_ER}, Articles 30–45"},
    {"rule_key": "exempt_supplies", "title": "Exempt supplies", "category": "treatment",
     "value": "Certain financial services; supply of bare land; local passenger transport; "
              "residential buildings (supplies after the first).",
     "effective_from": "2018-01-01", "source_ref": f"{_DL8}, Article 46; {_ER}, Articles 42–46"},
    {"rule_key": "reverse_charge", "title": "Reverse-charge mechanism", "category": "treatment",
     "value": "Imports of goods and services; supplies of specified goods (e.g. certain "
              "hydrocarbons) between registrants.",
     "effective_from": "2018-01-01", "source_ref": f"{_DL8}, Articles 48; {_ER}, Article 48"},
    {"rule_key": "registration_threshold_mandatory", "title": "Mandatory registration threshold",
     "category": "registration", "value": "AED 375,000", "effective_from": "2018-01-01",
     "source_ref": f"{_DL8}, Article 13; {_ER}, Article 7"},
    {"rule_key": "registration_threshold_voluntary", "title": "Voluntary registration threshold",
     "category": "registration", "value": "AED 187,500", "effective_from": "2018-01-01",
     "source_ref": f"{_DL8}, Article 17; {_ER}, Article 8"},
    {"rule_key": "return_filing", "title": "VAT return filing & payment deadline",
     "category": "procedures", "value": "Within 28 days of the end of the tax period (monthly or "
     "quarterly as assigned by the FTA).", "effective_from": "2018-01-01",
     "source_ref": f"{_DL8}, Articles 64; {_ER}, Articles 62, 64"},
    {"rule_key": "input_recovery", "title": "Input VAT recovery",
     "category": "recovery", "value": "Recoverable on taxable business supplies with valid tax "
     "invoices; blocked items include certain entertainment and specified motor vehicles.",
     "effective_from": "2018-01-01", "source_ref": f"{_DL8}, Articles 54–55; {_ER}, Articles 52–55"},
    {"rule_key": "designated_zones", "title": "Designated Zones", "category": "treatment",
     "value": "Specified fenced free zones treated as outside the UAE for certain goods supplies.",
     "effective_from": "2018-01-01", "source_ref": f"{_ER}, Articles 51; Cabinet Decision on Designated Zones"},
]


def seed_fta(db: Session) -> dict:
    """Idempotently seed official sources and baseline rules. Returns counts added."""
    added_sources = 0
    for s in SEED_SOURCES:
        exists = db.scalar(select(FtaSource).where(FtaSource.url == s["url"]))
        if exists:
            continue
        db.add(FtaSource(**s))
        added_sources += 1

    added_rules = 0
    for r in SEED_RULES:
        exists = db.scalar(select(VatRuleVersion).where(VatRuleVersion.rule_key == r["rule_key"]))
        if exists:
            continue
        db.add(VatRuleVersion(status="active", created_by="system:seed", **r))
        added_rules += 1

    db.commit()
    total_sources = db.scalar(select(FtaSource).order_by(FtaSource.created_at)) is not None
    return {"sources_added": added_sources, "rules_added": added_rules, "seeded": total_sources}
