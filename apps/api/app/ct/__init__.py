"""UAE Corporate Tax (CT) review — Federal Decree-Law No. 47 of 2022.

A sibling regime to the VAT domain. CT is assessed per entity, per tax period from
financial-statement figures (not per invoice), so it has its own `CorporateTaxReturn`
schema and rule engine. The regime-agnostic compliance primitives (Finding, verdict,
verification/validation) are shared via `app.compliance`.

⚠️  The rule set and its legal references are PROVISIONAL — a draft catalogue
(`docs/ct-compliance-brief.md`) pending UAE CT subject-matter-expert validation.
"""

from .rules import ALL_RULES, review_ct_return
from .schemas import CorporateTaxReturn, CTReviewResult, FreeZoneStatus, TaxpayerType

__all__ = [
    "ALL_RULES",
    "CTReviewResult",
    "CorporateTaxReturn",
    "FreeZoneStatus",
    "TaxpayerType",
    "review_ct_return",
]
