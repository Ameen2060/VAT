"""UAE FTA VAT Regulatory Update Monitoring & Update System.

Monitors official FTA / Ministry of Finance sources for VAT regulatory changes,
records them in a permanent change log with a NEW -> UNDER_REVIEW -> APPROVED ->
IMPLEMENTED workflow, and maintains an effective-dated, source-referenced VAT rule
registry so treatments are traceable and historical transactions stay protected.

Detection produces *signals* for human review only — nothing is applied to the live
VAT engine without authorised approval.
"""
