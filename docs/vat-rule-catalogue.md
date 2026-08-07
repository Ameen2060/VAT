# VAT Rule Catalogue

This is the human-readable catalogue of the deterministic checks the engine performs
(`apps/api/app/vat/rules.py`). **Please review and validate these as the VAT SME** —
the code is the single source of truth for the platform's verdicts, so any rule you
want changed, added, or re-graded starts here.

Severity → status mapping:

| Highest severity present | Compliance status | Risk level |
|--------------------------|-------------------|------------|
| High                     | **Fail**          | High       |
| Medium                   | **Warning**       | Medium     |
| Low                      | **Warning**       | Low        |
| None (info only)         | **Pass**          | Low        |

## Rules

| Rule ID | Severity | Checks | Legal basis |
|---------|----------|--------|-------------|
| INV-LABEL-001 | High | Document clearly displays "Tax Invoice" | Art. 59(1) ER |
| INV-NUM-001 | High | Sequential/unique invoice number present | Art. 59(1) ER |
| INV-DATE-001 | High | Date of issue present | Art. 59(1) ER |
| SUP-NAME-001 | High | Supplier name present | Art. 59(1) ER |
| SUP-ADDR-001 | Medium | Supplier address present | Art. 59(1) ER |
| SUP-TRN-001 | High | Supplier TRN present | Art. 59(1) ER |
| SUP-TRN-002 | High | Supplier TRN is a valid 15-digit number | Art. 59(1) ER |
| REC-NAME-001 | Medium | Recipient name present (full invoice) | Art. 59(1) ER |
| REC-TRN-002 | Medium | Recipient TRN valid if present | Art. 59(1) ER |
| SIMP-001 | High | Simplified invoice only if recipient unregistered **or** ≤ AED 10,000 | Art. 59(5) ER |
| CUR-001 | Medium | Foreign currency shows exchange rate / AED amounts | Art. 69 Decree-Law; Art. 59(1)(i) ER |
| RCM-001 | Medium | Reverse-charge statement present where RCM applies | Art. 48 Decree-Law |
| RCM-002 | High | Supplier has **not** charged VAT on a reverse-charge supply | Art. 48 Decree-Law |
| TRT-000 | Low | VAT treatment has been classified | Art. 3 Decree-Law |
| TRT-001 | High | Applied rate matches the classified treatment | Art. 3 / 45 / 46 Decree-Law |
| CALC-001 | High | Line VAT = net × rate (± AED 0.02) | Art. 56 ER (rounding) |
| CALC-002 | High | Net + VAT = gross | Art. 59(1) ER |
| CALC-003 | Medium | Header VAT ≈ 5% of net | Art. 56 ER |
| EXM-001 | Info | Exempt supply — input VAT not recoverable / apportion | Art. 46 Decree-Law |
| EXP-001 | Low | Zero-rated export needs retained evidence (90 days) | Art. 45(1) Decree-Law; Art. 30–31 ER |

## Known limitations (roadmap, not gaps to hide)

- **Time-of-supply / tax point** (Art. 25–26) is not yet enforced — needs payment &
  delivery dates the extraction layer will capture in Phase 1.
- **Designated Zone** goods-vs-services distinction (Art. 51) is stubbed pending the
  transaction-type classifier.
- **Input-tax apportionment** and **blocked input tax** (Art. 53 ER — entertainment,
  certain motor vehicles) are flagged informationally, not yet computed.
- **Credit/debit note** linkage to the original invoice (Art. 62) is modelled in the
  schema but not yet rule-checked.

These are deliberately sequenced for later phases and documented so nothing is
silently missing.
