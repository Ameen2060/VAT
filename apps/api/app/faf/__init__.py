"""UAE FTA Audit File (FAF) module.

Generates the official FTA VAT audit workbook ("FAF New Format") from a saved
VAT201 return: a *Required information* sheet, a *VAT Return* summary, and one
transaction-listing sheet per VAT201 box (Box 1, Out of Scope, Box 2-7, 9, 10).

The workbook is produced by populating the bundled official template so the
sheet names, headers, questionnaire text and formatting match the FTA file
exactly — only the values change.
"""

from .builder import FAF_TEMPLATE_PATH, build_faf_workbook

__all__ = ["build_faf_workbook", "FAF_TEMPLATE_PATH"]
