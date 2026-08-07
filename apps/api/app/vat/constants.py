"""UAE VAT domain constants and legal references.

Values reflect UAE VAT law in force. Where a figure can change by Cabinet Decision
(e.g. the standard rate), it is centralised here so a legislative change is a
one-line edit rather than a code hunt.

Primary sources:
  * Federal Decree-Law No. 8 of 2017 on VAT (the "Decree-Law")
  * Cabinet Decision No. 52 of 2017 — Executive Regulation (the "ER"), as amended
    by Cabinet Decision No. 46 of 2020 and No. 99 of 2022
"""

from __future__ import annotations

# ── Rates ────────────────────────────────────────────────────────────────────
STANDARD_RATE = 0.05  # Art. 3 Decree-Law
ZERO_RATE = 0.00      # Art. 45 Decree-Law (zero-rated supplies)

# ── Thresholds (AED) ─────────────────────────────────────────────────────────
MANDATORY_REGISTRATION_THRESHOLD = 375_000  # Art. 13 Decree-Law
VOLUNTARY_REGISTRATION_THRESHOLD = 187_500  # Art. 17 Decree-Law
# A simplified tax invoice is permitted where the recipient is not registered OR the
# consideration does not exceed this amount — Art. 59(5) ER.
SIMPLIFIED_INVOICE_MAX = 10_000

# ── TRN ──────────────────────────────────────────────────────────────────────
TRN_LENGTH = 15  # UAE Tax Registration Number is 15 digits

# ── Rounding ─────────────────────────────────────────────────────────────────
# Tax may be calculated and rounded to the nearest fils (2 decimals), using
# mathematical rounding — Art. 56 ER.
TAX_DECIMALS = 2
# Tolerance (AED) when comparing a stated VAT amount to the recomputed amount, to
# absorb legitimate per-line rounding differences.
CALC_TOLERANCE_AED = 0.02

# ── Legal reference catalogue ────────────────────────────────────────────────
# Human-readable citations attached to findings. Kept as data so the same string is
# reused everywhere and is easy to audit/update.
LEGAL_REFS: dict[str, str] = {
    "standard_rate": "Art. 3, Federal Decree-Law No. 8 of 2017",
    "zero_rated": "Art. 45, Federal Decree-Law No. 8 of 2017",
    "exempt": "Art. 46, Federal Decree-Law No. 8 of 2017",
    "tax_invoice_required": "Art. 65 & 67, Federal Decree-Law No. 8 of 2017",
    "full_invoice_particulars": "Art. 59(1), Executive Regulation (Cabinet Decision 52 of 2017)",
    "simplified_invoice_particulars": "Art. 59(5), Executive Regulation (Cabinet Decision 52 of 2017)",
    "simplified_invoice_conditions": "Art. 59(5), Executive Regulation (Cabinet Decision 52 of 2017)",
    "currency_conversion": "Art. 69, Federal Decree-Law No. 8 of 2017; Art. 59(1)(i) ER",
    "reverse_charge": "Art. 48, Federal Decree-Law No. 8 of 2017; Art. 3(1) & 48 ER",
    "input_tax_recovery": "Art. 54 & 55, Federal Decree-Law No. 8 of 2017",
    "blocked_input_tax": "Art. 53, Executive Regulation (Cabinet Decision 52 of 2017)",
    "rounding": "Art. 56, Executive Regulation (Cabinet Decision 52 of 2017)",
    "time_of_supply": "Art. 25–26, Federal Decree-Law No. 8 of 2017",
    "credit_note": "Art. 62, Federal Decree-Law No. 8 of 2017; Art. 60 ER",
    "export_zero_rating": "Art. 45(1) Decree-Law; Art. 30 & 31 ER",
    "designated_zone": "Art. 51, Federal Decree-Law No. 8 of 2017; Art. 51 ER",
}
