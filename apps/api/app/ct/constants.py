"""UAE Corporate Tax (CT) domain constants and legal references.

Values reflect UAE Corporate Tax law as summarised in ``docs/ct-compliance-brief.md``.
Where a figure can change by Cabinet/Ministerial Decision it is centralised here so a
legislative change is a one-line edit.

Primary source:
  * Federal Decree-Law No. 47 of 2022 on the Taxation of Corporations and Businesses
    (the "CT Law"), effective for tax periods beginning on/after 1 June 2023, plus the
    implementing Cabinet and Ministerial Decisions.

⚠️  PROVISIONAL CITATIONS. Every entry in ``LEGAL_REFS`` is a *draft* legal basis and
carries a provisional marker until validated by a UAE CT subject-matter expert. The
platform's "trust before cleverness" principle means these must be confirmed against the
official gazette before the engine's verdicts are relied upon in an FTA context.
"""

from __future__ import annotations

# ── Rates ────────────────────────────────────────────────────────────────────
SMALL_PROFITS_THRESHOLD = 375_000   # AED — taxable income at/below this is taxed 0%
STANDARD_CT_RATE = 0.09             # 9% on taxable income above the threshold
DMTT_RATE = 0.15                    # Domestic Minimum Top-up Tax (Pillar Two)
DMTT_GLOBAL_REVENUE_EUR = 750_000_000  # MNE consolidated global revenue in-scope for DMTT

# ── Small Business Relief (SBR) ──────────────────────────────────────────────
SBR_REVENUE_MAX = 3_000_000         # AED — revenue ceiling to elect SBR
SBR_SUNSET_DATE = "2026-12-31"      # SBR only for tax periods ending on/before this date

# ── Free Zone (QFZP) de minimis ──────────────────────────────────────────────
QFZP_DE_MINIMIS_ABS = 5_000_000     # AED — absolute non-qualifying revenue cap
QFZP_DE_MINIMIS_PCT = 0.05          # ...or 5% of total revenue, whichever is LOWER

# ── Deduction limitations ────────────────────────────────────────────────────
INTEREST_EBITDA_PCT = 0.30          # net interest deductible up to 30% of tax-EBITDA
INTEREST_DE_MINIMIS = 12_000_000    # AED — safe-harbour: always deduct up to this
ENTERTAINMENT_DEDUCTIBLE_PCT = 0.50  # entertainment expenditure is 50% deductible
LOSS_OFFSET_MAX_PCT = 0.75          # tax-loss offset capped at 75% of taxable income

# ── Compliance thresholds ────────────────────────────────────────────────────
AUDITED_FS_REVENUE_THRESHOLD = 50_000_000  # AED — audited FS required above this
NATURAL_PERSON_TURNOVER_THRESHOLD = 1_000_000  # AED — natural person becomes taxable
TP_LOCAL_FILE_TAXPAYER_REVENUE = 200_000_000   # AED — taxpayer revenue master/local-file trigger
TP_LOCAL_FILE_MNE_REVENUE = 3_150_000_000      # AED — MNE group consolidated revenue trigger
# Return-DISCLOSURE thresholds (distinct from the master/local-file thresholds above):
# a schedule is filed WITH the return when these aggregates are exceeded (CTGTXR1 §16).
TP_RP_DISCLOSURE_AGGREGATE = 40_000_000        # AED — related-party transactions aggregate
TP_CONNECTED_DISCLOSURE = 500_000              # AED — connected-person payments aggregate
# ⚠️ VERIFY the AED 40M / 500k figures against FTA guide CTGTXR1 before production trust.
CT_RETURN_FILING_MONTHS = 9         # return + payment due within 9 months of period end
LATE_REGISTRATION_PENALTY_AED = 10_000

# ── TRN ──────────────────────────────────────────────────────────────────────
TRN_LENGTH = 15  # UAE Tax Registration Number is 15 digits

# ── Tolerance ────────────────────────────────────────────────────────────────
# AED tolerance when comparing a stated tax figure to the recomputed amount.
CALC_TOLERANCE_AED = 1.00

# ── Registration deadline schedule (FTA Decision No. 3 of 2024) ──────────────
# For resident juridical persons that held a licence and were incorporated/established
# BEFORE 1 March 2024: the registration deadline is driven by the MONTH the licence was
# issued (regardless of the year of issuance). Month number (1-12) → ISO deadline date.
REGISTRATION_DEADLINE_BY_LICENCE_MONTH: dict[int, str] = {
    1: "2024-05-31",   # January
    2: "2024-05-31",   # February
    3: "2024-06-30",   # March
    4: "2024-06-30",   # April
    5: "2024-07-31",   # May
    6: "2024-08-31",   # June
    7: "2024-09-30",   # July
    8: "2024-10-31",   # August
    9: "2024-10-31",   # September
    10: "2024-11-30",  # October
    11: "2024-11-30",  # November
    12: "2024-12-31",  # December
}
# Persons incorporated ON/AFTER 1 March 2024 must register within this many months.
REGISTRATION_WINDOW_MONTHS_NEW = 3

# ── Legal reference catalogue (PROVISIONAL) ──────────────────────────────────
_PROVISIONAL = " · PROVISIONAL — pending SME validation"

_LEGAL_REFS_RAW: dict[str, str] = {
    "registration": "Art. 51, Federal Decree-Law No. 47 of 2022; FTA Decision No. 3 of 2024 (deadlines)",
    "late_registration_penalty": "Cabinet Decision on administrative penalties (CT)",
    "filing": "Art. 53 & 48, Federal Decree-Law No. 47 of 2022 (return & payment within 9 months)",
    "rates": "Art. 3, Federal Decree-Law No. 47 of 2022",
    "small_business_relief": "Art. 21, Federal Decree-Law No. 47 of 2022; Ministerial Decision No. 73 of 2023",
    "free_zone": "Art. 3 & 18, Federal Decree-Law No. 47 of 2022; Cabinet Decision No. 100 of 2023",
    # Qualifying/Excluded activities: MD 265/2023, superseded by MD 229/2025 for periods
    # on/after 1 Jan 2025 (date-effective — verify cutover).
    "free_zone_activities": "Ministerial Decision No. 265 of 2023 (→ No. 229 of 2025 from 1 Jan 2025)",
    "free_zone_de_minimis": "Cabinet Decision No. 100 of 2023 (de minimis requirements)",
    "free_zone_audited_fs": "Ministerial Decision No. 82 of 2023 (audited financial statements)",
    "interest_limitation": "Art. 30-31, Federal Decree-Law No. 47 of 2022; Ministerial Decision No. 126 of 2023",
    "entertainment": "Art. 32, Federal Decree-Law No. 47 of 2022",
    "tax_losses": "Art. 37-39, Federal Decree-Law No. 47 of 2022",
    "participation_exemption": "Art. 23, Federal Decree-Law No. 47 of 2022; Ministerial Decision No. 116 of 2023",
    "transfer_pricing": "Art. 34-36, Federal Decree-Law No. 47 of 2022; Ministerial Decision No. 97 of 2023",
    "tp_disclosure": "Art. 55, Federal Decree-Law No. 47 of 2022; FTA Guide CTGTXR1",
    "audited_financials": "Ministerial Decision No. 82 of 2023",
    "foreign_tax_credit": "Art. 47, Federal Decree-Law No. 47 of 2022",
    "dmtt": "Federal Decree-Law No. 60 of 2023; Cabinet Decision No. 142 of 2024 (Domestic Minimum Top-up Tax)",
}

# Participation exemption (Art. 23) conditions.
PARTICIPATION_MIN_OWNERSHIP_PCT = 0.05      # ≥5% ownership...
PARTICIPATION_MIN_ACQUISITION_COST = 4_000_000  # ...OR acquisition cost > AED 4M
PARTICIPATION_MIN_HOLDING_MONTHS = 12       # 12-month holding period

# Public catalogue: every citation carries the provisional marker.
LEGAL_REFS: dict[str, str] = {k: v + _PROVISIONAL for k, v in _LEGAL_REFS_RAW.items()}
