# UAE Corporate Tax (CT) — Compliance Brief

A domain reference for UAE Corporate Tax, written to mirror the structure of the VAT
side of this platform so it can double as the source material for a future **CT rule
engine** and **CT knowledge corpus**.

> **Accuracy note.** Rates, thresholds, and sunset dates below were verified against
> the FTA (tax.gov.ae), the Ministry of Finance (mof.gov.ae), and Big-Four summaries
> in **August 2026** (see Sources). Article numbers and the specific Ministerial /
> Cabinet Decision numbers are drawn from the legislation as I know it and **must be
> confirmed against the official gazette before they are wired into a rule engine as
> `legal_ref` citations** — the same "trust before cleverness" bar the VAT engine holds.

---

## 1. The regime in one paragraph

UAE Corporate Tax is a **federal tax on business profits**, introduced by
**Federal Decree-Law No. 47 of 2022 on the Taxation of Corporations and Businesses**.
It applies to **tax periods (financial years) beginning on or after 1 June 2023**.
Unlike VAT — a transactional tax assessed per invoice — CT is an **annual, entity-level
tax on net accounting profit** (per IFRS) after prescribed tax adjustments. This is the
single most important modelling difference for the platform: **the unit of review is an
entity's tax period, not an invoice.**

---

## 2. Rates

| Band | Rate | Applies to |
|------|------|------------|
| Taxable income ≤ **AED 375,000** | **0%** | All taxable persons (the "small profits" floor) |
| Taxable income > AED 375,000 | **9%** | The excess above AED 375,000 |
| Large MNEs — **DMTT** | **15%** | UAE entities of MNE groups with consolidated global revenue **≥ EUR 750M** in ≥2 of the prior 4 FYs; effective for FYs starting **on/after 1 Jan 2025** |
| Qualifying Free Zone Person — Qualifying Income | **0%** | See §5 |
| Qualifying Free Zone Person — other income | **9%** | Income that is not Qualifying Income |

The 15% Domestic Minimum Top-up Tax (DMTT) implements the OECD Pillar Two / GloBE rules
(a top-up to a 15% effective rate). It is a **separate computation and return** from the
standard CT return, and out of scope for a first CT module — but worth a discriminator flag.

---

## 3. Who is taxable

**Resident persons**
- UAE-incorporated juridical persons (LLCs, PJSCs, etc.), including Free Zone entities.
- Foreign juridical persons **effectively managed and controlled** in the UAE.
- **Natural persons** conducting a business/business activity in the UAE with total
  turnover **> AED 1,000,000** in a Gregorian calendar year (Cabinet Decision No. 49 of 2023).
  Wages, personal investment income, and personal real-estate income are excluded.

**Non-resident persons** — taxable where they have:
- a **Permanent Establishment (PE)** in the UAE, or
- **UAE-sourced income**, or
- a **nexus** in the UAE (e.g. income from UAE immovable property).

**Exempt persons** (Art. 4) — government entities; government-controlled entities;
extractive businesses; non-extractive natural-resource businesses; qualifying public
benefit entities; qualifying investment funds; public/private pension & social security
funds; and certain wholly-owned UAE subsidiaries of exempt persons. Most exemptions
require **registration/approval and ongoing conditions** — exemption is not automatic.

---

## 4. Registration & filing (the compliance calendar)

| Obligation | Rule |
|------------|------|
| **Registration** | Every taxable person must register for CT and obtain a **Tax Registration Number (TRN)** via EmaraTax — including Free Zone persons and most exempt/relief claimants. |
| Registration deadline (resident juridical, incorporated before 1 Mar 2024) | Staggered by **month of licence issuance** (FTA Decision No. 3 of 2024); earliest deadline was **31 May 2024**. |
| Registration deadline (incorporated on/after 1 Mar 2024) | Within **3 months** of incorporation. |
| **Late-registration penalty** | **AED 10,000**. |
| **Penalty-waiver initiative** | The FTA waives the late-registration penalty if the person files their **first CT return (or annual declaration) within 7 months** of the end of the **first** tax period (instead of the usual 9). |
| **CT return filing** | **One return per tax period**, filed electronically via EmaraTax **within 9 months** of the end of the tax period. |
| **CT payment** | Due **within the same 9 months** — no provisional/advance instalments. |
| **Record keeping** | Retain records/documents for **7 years** after the tax period. |
| **Audited financial statements** | Required for taxable persons with revenue **> AED 50M**, and for **all QFZPs** (Ministerial Decision No. 82 of 2023). |

---

## 5. Free Zone — Qualifying Free Zone Person (QFZP)

A **QFZP** pays **0% on Qualifying Income** and **9%** on income that is not qualifying.
Governing texts: Art. 3 & 18 of the Decree-Law; **Cabinet Decision No. 100 of 2023**
(qualifying income) and **Ministerial Decision No. 265 of 2023** (qualifying activities).

**All conditions must be met to keep QFZP status:**
1. Maintain **adequate substance** in the Free Zone.
2. Derive **Qualifying Income** (from qualifying activities / transactions with other Free Zone persons).
3. Has **not elected** to be subject to standard CT.
4. Complies with the **arm's-length principle and transfer-pricing** documentation.
5. Maintains **audited financial statements**.
6. Satisfies the **de minimis** requirement.

**De minimis:** non-qualifying revenue must not exceed the **lower of AED 5,000,000 or
5% of total revenue**. Breach it (or fail any condition) and the person **loses QFZP
status for that tax period and the following 4 tax periods** — taxed at 9% on all
taxable income. **Excluded activities** and **qualifying activities** are enumerated in
MD 265 of 2023 (e.g. manufacturing, holding of shares/securities, fund management, HQ
services to related parties are qualifying; most transactions with mainland natural
persons, banking, insurance, and certain IP income are excluded).

---

## 6. Small Business Relief (SBR)

- **Elective** relief under Art. 21 / **Ministerial Decision No. 73 of 2023**.
- Available where **revenue ≤ AED 3,000,000** in the relevant tax period **and all
  previous** tax periods.
- **Time-limited:** applies to tax periods **ending on or before 31 December 2026**.
- Effect: the person is **treated as having no taxable income** for the period and gets
  **simplified compliance** (still must register and file, but no full computation; cannot
  carry forward losses or excess interest arising in a relief period).
- **Not available** to **Qualifying Free Zone Persons** or **members of MNE Groups**.

> **Platform note:** SBR is a checkbox that short-circuits most of the computation. A CT
> rule engine should test SBR eligibility **first** and, if elected, skip the profit-
> adjustment rules while still emitting registration/filing findings.

---

## 7. Computing taxable income (the core of a CT rule set)

Start from **accounting net profit/loss** in IFRS-compliant financial statements, then
apply tax adjustments (Art. 20 onward):

**Exclude (exempt) income**
- Dividends/profit distributions from UAE juridical persons.
- **Participation exemption** (Art. 23; Ministerial Decision No. 116 of 2023) — dividends
  and gains from a **qualifying shareholding**: ≥ **5% ownership** *or* acquisition cost
  ≥ **AED 4M**, held ≥ **12 months**, with a **subject-to-tax** test (~9%+).
- **Foreign PE exemption** (Art. 24, elective).

**Deductions — allowed**
- Expenditure incurred **wholly and exclusively** for business, that is **not capital** in nature.

**Deductions — limited or denied**
| Item | Treatment |
|------|-----------|
| **Net interest expense** | Deductible up to **30% of tax-EBITDA** (General Interest Deduction Limitation Rule); **de minimis AED 12,000,000**; excess carried forward up to 10 years (Ministerial Decision No. 126 of 2023). |
| **Entertainment expenditure** | **50% deductible** (Art. 32). |
| Fines/penalties, bribes, dividends paid, the CT itself, recoverable input VAT, donations to non-qualifying recipients | **Not deductible**. |

**Tax losses** (Art. 37–39) — carried forward **indefinitely**; offset capped at **75% of
taxable income** in a period; transferable within a group (≥75% common ownership), subject
to continuity-of-ownership/business tests.

---

## 8. Related parties, transfer pricing, tax groups

- **Arm's-length principle** on all related-party and connected-person transactions
  (Art. 34–36), OECD-aligned.
- **TP documentation** — **master file + local file** required where the taxable person is
  a constituent of an MNE group with consolidated revenue ≥ **AED 3.15bn**, or has its own
  revenue ≥ **AED 200M** (Ministerial Decision No. 97 of 2023). A **related-party
  transactions disclosure form** accompanies the return above thresholds.
- **Tax Group** (Art. 40) — resident juridical persons may form a single taxable group
  where a parent holds ≥ **95%** of capital/voting/profit, same FY and accounting standards,
  and none is exempt or a QFZP. Files **one consolidated return**.

## 9. General Anti-Abuse Rule (GAAR)

Art. 50 lets the FTA counteract arrangements whose **main purpose** is a CT advantage not
aligned with the law's intent. Relevant as an advisory/AI flag, not a deterministic rule.

---

## 10. What this means for a CT module (mapping to the platform)

| VAT platform concept | CT equivalent |
|----------------------|---------------|
| `Invoice` (transactional) | **`CorporateTaxReturn`** — entity + tax period + financial-statement figures + adjustments |
| Per-invoice review | **Per-entity, per-tax-period** review |
| TRN 15-digit format check | CT **TRN presence/registration-deadline** check |
| VAT rate 5% / treatment match | **Rate-band** (0%/9%), **QFZP 0%**, **SBR** short-circuit |
| Reverse-charge triggers | **Interest limitation**, **entertainment 50%**, **exempt-income** exclusions, **de minimis** |
| `legal_ref` → VAT decree articles | `legal_ref` → **Decree-Law 47/2022** articles + Cabinet/Ministerial Decisions |

**Candidate deterministic CT rules** (sketch, IDs following the VAT convention):

| Rule ID | Severity | Checks |
|---------|----------|--------|
| CT-REG-001 | High | Entity is CT-registered / has a CT TRN |
| CT-REG-002 | High | Registered by the applicable deadline (else AED 10k penalty exposure) |
| CT-FILE-001 | High | Return filed within 9 months of period end |
| CT-SBR-001 | Info | Revenue ≤ AED 3M and period ends ≤ 31 Dec 2026 → SBR available |
| CT-SBR-002 | Medium | SBR elected but entity is QFZP or MNE member → **ineligible** |
| CT-RATE-001 | High | 0% applied only up to AED 375,000; 9% on the excess |
| CT-FZ-001 | High | QFZP de minimis: non-qualifying revenue ≤ lower of AED 5M / 5% |
| CT-FZ-002 | Medium | QFZP maintains audited financial statements |
| CT-INT-001 | Medium | Net interest deduction ≤ 30% tax-EBITDA (de minimis AED 12M) |
| CT-ENT-001 | Low | Entertainment expense deducted at ≤ 50% |
| CT-LOSS-001 | Medium | Loss offset ≤ 75% of taxable income |
| CT-TP-001 | Medium | TP disclosure / master+local file where thresholds met |
| CT-AUDIT-001 | Medium | Audited FS where revenue > AED 50M |

These are a **starting catalogue for SME review**, not a shipped rule set — the same way
`docs/vat-rule-catalogue.md` is validated before the engine is trusted.

---

## Sources

- [FTA — Corporate Tax topics](https://tax.gov.ae/en/taxes/corporate.tax/corporate.tax.topics.aspx)
- [FTA — Small Business Relief](https://tax.gov.ae/en/taxes/corporate.tax/corporate.tax.topics/small.business.relief.23.aspx)
- [Ministry of Finance — Corporate Tax](https://mof.gov.ae/en/public-finance/tax/corporate-tax-in-the-uae/)
- [Ministry of Finance — Domestic Minimum Top-up Tax](https://mof.gov.ae/uae-domestic-minimum-top-up-tax/)
- [FTA — Free Zone Persons guide](https://tax.gov.ae/en/media.centre/news/federal.tax.authority.issues.corporate.tax.guide.on.free.zone.persons.aspx)
- [PwC — UAE Corporate income tax](https://taxsummaries.pwc.com/united-arab-emirates/corporate/taxes-on-corporate-income)
- [EY — UAE issues DMTT legislation](https://www.ey.com/en_gl/technical/tax-alerts/uae-issues-domestic-minimum-top-up-tax-legislation)
