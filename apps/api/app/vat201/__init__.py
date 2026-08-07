"""UAE VAT Return (VAT201) generation from a period's transactions.

Transactions are classified into the FTA VAT201 boxes purely from their data (tax
code / rate / document type / direction / emirate) — no per-company template. The
engine computes taxable values, output/input/reverse-charge VAT and the net return,
keeps each box's contributing transactions for drill-down, and runs pre-submission
validation checks.
"""
