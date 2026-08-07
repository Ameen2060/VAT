# UAE Corporate Tax — Structured Knowledge Model

The authoritative domain foundation for the CT compliance module. Everything the
calculation engine, validation engine, return form, and schedules are built from traces
back to this document, and every material fact here carries a **legal basis** and a
**source**. Compiled August 2026 from the primary authorities named in the project brief.

> **Authority hierarchy (ties broken top-down):**
> 1. **Federal Tax Authority — tax.gov.ae** (authoritative; the CT Guides are the field-level source)
> 2. **Ministry of Finance — mof.gov.ae** (legislation & Decisions)
> 3. **Deloitte / PwC** (implementation guidance only — never overrides 1–2)
>
> **Trust stance.** Facts confirmed against an FTA/MoF primary source are unmarked.
> Facts resting on advisory-firm commentary or not re-verified line-by-line against the
> gazette are tagged **⚠️ VERIFY** and collected in the [Verification backlog](#20-verification-backlog).
> No rule enters the engine as trusted until it clears that backlog with SME sign-off.

Companion docs: [ct-architecture.md](ct-architecture.md) · [ct-database-schema.md](ct-database-schema.md) · [ct-roadmap.md](ct-roadmap.md) · [ct-compliance-brief.md](ct-compliance-brief.md).

---

## 1. Regime overview

| Attribute | Value | Basis |
|-----------|-------|-------|
| Governing law | **Federal Decree-Law No. 47 of 2022** on the Taxation of Corporations and Businesses ("CT Law") | FTA / MoF |
| Effective from | Tax periods beginning **on or after 1 June 2023** | Art. 69 |
| Basis of assessment | **Entity-level, per tax period**, on net accounting profit (IFRS) as adjusted — *not* transactional | Art. 20 |
| Administration | Self-assessment, filed and paid via **EmaraTax** | FTA |

This entity/period basis is the core modelling contrast with VAT and is why CT has its
own `CorporateTaxReturn` domain rather than reusing the invoice model.

## 2. Rates & Domestic Minimum Top-up Tax (DMTT)

| Band | Rate | Basis / source |
|------|------|----------------|
| Taxable income ≤ **AED 375,000** | **0%** | Art. 3 · [PwC](https://taxsummaries.pwc.com/united-arab-emirates/corporate/taxes-on-corporate-income) |
| Taxable income > AED 375,000 | **9%** | Art. 3 |
| QFZP — Qualifying Income | **0%** | Art. 3(2) |
| QFZP — other taxable income | **9%** | Art. 3(2) |
| **DMTT** (large MNEs) | **15%** effective minimum | **Federal Decree-Law No. 60 of 2023** + **Cabinet Decision No. 142 of 2024** · [gazette PDF](https://tax.gov.ae/Datafolder/Files/Legislation/Cabinet-Decision-No-142-of-2024-on-Top-up-Tax-on-MNEs.pdf) |

**DMTT scope:** MNE groups with consolidated global revenue **≥ EUR 750M in ≥2 of the 4**
preceding years; financial years starting **on/after 1 January 2025**. Separate
computation and return from standard CT.

## 3. Scope — who is taxable, who is exempt

**Taxable Persons** (Art. 11):
- **Resident — juridical:** UAE-incorporated companies (incl. Free Zone entities); foreign juridical persons **effectively managed and controlled** in the UAE.
- **Resident — natural person:** conducting business in the UAE with **turnover > AED 1,000,000** in a Gregorian calendar year (Cabinet Decision No. 49 of 2023). Salary, personal investment, and personal real-estate income are excluded.
- **Non-Resident** (Art. 11(4)): has a **Permanent Establishment**, a **nexus** (e.g. UAE immovable property), or **State-sourced income** in the UAE.

**Exempt Persons** (Art. 4, registration/approval + conditions apply): Government Entities;
Government-Controlled Entities; Extractive and Non-Extractive Natural-Resource Businesses;
Qualifying Public Benefit Entities; Qualifying Investment Funds; public/private pension &
social security funds; certain wholly-owned UAE subsidiaries of the above.

## 4. Compliance calendar — registration, filing, payment, retention

| Obligation | Rule | Basis |
|------------|------|-------|
| **Registration** | All Taxable Persons register via EmaraTax and obtain a CT TRN | Art. 51 |
| Deadline — resident juridical (pre-1 Mar 2024) | By **month of earliest licence issuance** (see table) | FTA Decision No. 3 of 2024 |
| Deadline — incorporated on/after 1 Mar 2024 | **3 months** from incorporation | FTA Decision No. 3 of 2024 |
| Deadline — natural persons | **31 March** of the year following the year turnover exceeded AED 1M | FTA Decision No. 3 of 2024 |
| Deadline — non-resident PE/nexus | Own windows (PE pre-1 Mar: 9 mo; nexus: by 31 May 2024; on/after: 6 mo / 3 mo) | FTA Decision No. 3 of 2024 |
| **Late-registration penalty** | **AED 10,000** | Cabinet Decision No. 10 of 2024 (amending CD 75/2023) |
| **Penalty waiver** | Waived/refunded if the **first CT return is filed within 7 months** of the first tax-period end (automatic) | [FTA news](https://tax.gov.ae/en/media.centre/news/federal.tax.authority.to.waive.penalty.for.late.corporate.tax.registration.aspx) |
| **Tax period** | The Financial Year (12 months); first period = first FY on/after 1 Jun 2023 | Art. 57, 69 |
| Change of tax period | Apply ≤ **6 months** after the original period end | Art. 58 (per FTA guidance) |
| **Return filing** | One return per period, **within 9 months** of period end, via EmaraTax | Art. 53 |
| **Payment** | CT payable **within the same 9 months** | Art. 48 |
| **Record retention** | **7 years** after the tax period | Art. 56 ⚠️ VERIFY exact years vs Tax Procedures Law |

### Registration deadline schedule — FTA Decision No. 3 of 2024 (resident juridical, pre-1 Mar 2024)
| Month of earliest licence issuance | Deadline |
|---|---|
| Jan – Feb | 31 May 2024 |
| Mar – Apr | 30 Jun 2024 |
| May | 31 Jul 2024 |
| Jun | 31 Aug 2024 |
| Jul | 30 Sep 2024 |
| Aug – Sep | 31 Oct 2024 |
| Oct – Nov | 30 Nov 2024 |
| Dec | 31 Dec 2024 |
| No licence at 1 Mar 2024 | 3 months (by 31 May 2024) |

> This schedule is implemented in `app/ct/constants.py` and **matches the FTA Decision** —
> confirmed by this research pass.

## 5. Taxable-income computation

**Starting point:** Accounting net profit/loss from standalone IFRS (or IFRS-for-SMEs /
cash basis where eligible) financial statements — Art. 20; **Ministerial Decision No. 134
of 2023** (general rules); accounting standards per **Ministerial Decision No. 114 of
2023**. The engine then applies adjustments:

**Permanent differences** (never reverse): exempt dividends (Art. 22); participation-exempt
income/gains (Art. 23); non-deductibles (Art. 33); the disallowed 50% of entertainment
(Art. 32).

**Temporary/timing differences** (reverse over time): tax vs accounting depreciation;
provisions/accruals deductible when incurred; unrealised gains/losses under a
realisation-basis election.

### Exempt income
| Item | Condition | Basis |
|------|-----------|-------|
| UAE dividends | From a UAE resident juridical person — fully exempt, no minimum holding | Art. 22 |
| **Participation exemption** | **≥ 5% ownership** *or* acquisition cost **> AED 4M**; **12-month** holding; **subject-to-tax ≥ 9%** | Art. 23 + Ministerial Decision No. 116 of 2023 |
| Foreign PE exemption | Elective; foreign PE taxed **≥ 9%** abroad | Art. 24 |

### Deductions
- **General rule (Art. 28):** deductible if **not capital** in nature and **wholly and exclusively** for business.
- **Interest limitation (GIDLR):** net interest deductible up to the **higher of 30% of tax-EBITDA or AED 12,000,000** (safe harbour); excess carried forward **10 tax periods**; a separate **SIDLR** targets related-party financing of dividends/buybacks/acquisitions. Basis: Art. 30–31 + **Ministerial Decision No. 126 of 2023**.
- **Entertainment (Art. 32):** **50%** deductible.
- **Non-deductible (Art. 33):** fines/penalties, bribes, dividends paid, the CT itself, donations to non-qualifying entities, expenditure deriving exempt income, and the disallowed 50% of entertainment. ⚠️ VERIFY the itemised Art. 33 list against the FTA law text.
- **Realisation basis (Art. 20(3)(b); MD 134/2023):** election to recognise gains/losses only on realisation (all fair-valued items, or capital-account items only). First tax period only; **irrevocable** save exceptional circumstances.
- **Tax depreciation:** feeds accounting-income adjustments; there is **no separate FTA "tax depreciation schedule"** in the return.

## 6. Tax losses (Art. 37–39)

| Rule | Value |
|------|-------|
| Carryforward | **Indefinite** |
| Offset cap | **75%** of taxable income of the period |
| Carryback | **Not permitted** |
| Ownership continuity | Maintain **≥ 50%** ownership from loss period to offset period (else business-continuity test) — Art. 39 |
| Group transfer | Between UAE resident group members with **≥ 75%** common ownership — Art. 38 |

## 7. Reliefs & elections (with irrevocability)

Source for the election mechanics: FTA guide **CTGTXR1** §3.2/§5.

| Election / relief | Availability | Revocable? | Basis |
|-------------------|--------------|-----------|-------|
| **Small Business Relief** | Revenue ≤ **AED 3M** (current + all prior periods); periods **ending ≤ 31 Dec 2026**; not QFZP, not MNE-group | **Annual** | Art. 21 + MD 73/2023 |
| Realisation basis | First tax period | Irrevocable* | Art. 20(3) + MD 134/2023 |
| Transitional rules (immovable / intangible / financial assets held at cost) | First tax period; not if cash basis | Irrevocable* | MD 120/2023 |
| Transfers within a Qualifying Group | When group conditions met | Irrevocable* (applies to all such transfers) | Art. 26 + MD 132/2023 |
| Business Restructuring Relief | Per qualifying transaction | Per-transaction election | Art. 27 + MD 133/2023 |
| Foreign PE exemption | Annual | Annual | Art. 24 |

\* except exceptional circumstances with FTA approval.

**SBR trade-offs:** while elected — treated as nil taxable income, simplified compliance,
but **no loss carryforward and no interest-limitation carryforward** for those periods.

## 8. Free Zone — Qualifying Free Zone Person (QFZP)

**Conditions (all required)** — Art. 18 + Cabinet Decision No. 100 of 2023:
1. **Adequate substance** in the Free Zone (core income-generating activity, assets, staff, opex).
2. Derives **Qualifying Income**.
3. Has **not elected** standard CT.
4. Complies with **arm's-length / TP** documentation.
5. Maintains **audited financial statements**.
6. Meets the **de minimis** requirement.

**De minimis:** non-qualifying revenue ≤ **lower of AED 5,000,000 or 5% of total revenue**.

**Qualifying vs Excluded activities:** **Ministerial Decision No. 265 of 2023** — **⚠️ but
Ministerial Decision No. 229 of 2025 appears to supersede MD 265 for tax periods on/after
1 Jan 2025** ([MoF PDF](https://mof.gov.ae/wp-content/uploads/2025/09/EN-Ministerial-Decision-No.-229-of-2025-Regarding-Qualifying-Activities-and-Excluded-Activities.pdf)). The module must be **date-effective**: MD 265 for earlier periods, MD 229 thereafter. VERIFY the precise cutover.

**Breach consequence:** failing de minimis *or any* condition → **loses QFZP status for that
tax period and the following four (5 periods total)**, taxed at 9% throughout — Art. 18(2).

**Audited FS mandate:** required for all QFZPs (and any person with revenue > AED 50M) —
Ministerial Decision No. 82 of 2023; a further audit-requirement MD (No. 84 of 2025 per
commentary ⚠️ VERIFY the number).

## 9. Tax groups (Art. 40–42)

- Two or more **UAE resident juridical persons** → a single Taxable Person, headed by a Parent.
- **95%** condition: Parent holds ≥ 95% of **capital, voting rights, and profits/net assets** (direct or indirect).
- No member may be an **Exempt Person** or **QFZP**; all share the **same financial year and accounting standards**.
- Files a **single consolidated return**; intra-group transactions eliminated; losses shared within the group.

## 10. Related parties, connected persons & transfer pricing

| Concept | Definition / rule | Basis |
|---------|-------------------|-------|
| **Related Party** | 4th-degree kinship (natural persons); or ≥ **50%** ownership/control between persons; a person and its PE; trust/foundation parties | Art. 35 |
| **Connected Person** | An **owner**, **director/officer** of the taxable person, or a Related Party of either; payments deductible only at **market value** and wholly/exclusively for business | Art. 36 |
| Arm's-length principle | Required on all RP/connected transactions; **5 OECD methods** (CUP, Resale, Cost-Plus, TNMM, Profit-Split) + others if none apply | Art. 34 |
| **Master File + Local File** | Required if revenue **≥ AED 200M** *or* MNE group consolidated revenue **≥ AED 3.15bn**; **retained**, produced within **30 days** of FTA request (not filed) | Ministerial Decision No. 97 of 2023 |
| **RP disclosure schedule** | Filed **with the return** where RP transactions aggregate **> AED 40M** | CTGTXR1 §16.1 |
| **Connected-persons schedule** | Filed with the return where payments aggregate **> AED 500,000** | CTGTXR1 §16.2 |

## 11. Foreign Tax Credit (Art. 47)

Credit for foreign tax on income also taxed in the UAE, **capped at the UAE CT on that same
income**; **no carryforward or carryback** — unused credit is lost.

## 12. The CT Return — structure (FTA guide CTGTXR1, Nov 2024)

The return is an **adaptive online form in EmaraTax** (no offline upload). It has **nine
parts**; the Parent files for a Tax Group. Source: [CTGTXR1 landing](https://tax.gov.ae/en/content/corporate.tax.guide.ctgtxr1.aspx) · [PDF](https://tax.gov.ae/Datafolder/Files/Guides/CT/CT-Returns-EN-11-11-2024.pdf).

| Part | Name | Contents |
|------|------|----------|
| A | Taxable Person information | Pre-populated identity + tailoring questions (partnership, FS basis, Free Zone, Tax Group, DTA) |
| B | Elections | The six elections (§7) |
| C | Accounting Schedule | Income Statement, OCI, Balance Sheet, Audit sub-part (disclosure only; does not feed the computation) |
| D | Accounting adjustments & Exempt Income | Equity method, realisation basis, transitional rules, exempt income, participation & foreign-PE exemption |
| E | Reliefs | Qualifying Group transfers (Art. 26), Business Restructuring Relief (Art. 27) |
| F | Other adjustments | Non-deductibles (Art. 28/33), **interest limitation (Art. 30)**, RP/connected-person TP adjustments, prior-period error ≤ AED 10k |
| G | Tax Liability & Tax Credits | Taxable income, tax losses (b/f, used, transferred), CT liability (0%/9%, QFZP split), foreign tax credit, **CT payable** |
| H | Review & Declaration | Preparer, authority, declaration, signature |
| I | Schedules | The 20 conditional schedules below |

### The 20 conditional schedules (CTGTXR1 §12–§22)
Free Zone · Free Zone IP income · UAE Dividends · Foreign PE · Tax Credit (FTC) ·
Related Party Transactions (> AED 40M) · Connected Persons (> AED 500k) · Tax Losses ·
Tax Group Losses · Participation Exemption · **Interest Capping** (net interest > AED 12M) ·
Transfers within a Qualifying Group · Business Restructuring Relief · Transitional Rules
(Immovable / Intangible / Financial assets — 3 schedules) · Income not reported in P&L ·
Unrealised gains/losses · Previously-deferred unrealised now realised · **Attachments**
(missing documents require a stated reason).

> **Modelling note:** map business concepts to FTA-named schedules — "interest limitation"
> = Interest Capping (#11); "group relief" = Qualifying-Group transfers + Tax-Group Losses;
> "free-zone qualifying income" = Free Zone Schedule. **Do not invent a standalone "tax
> depreciation schedule"** — the FTA return has none.

### Field-level thresholds embedded in the return
- RP transactions aggregate **> AED 40M** → Related Party schedule.
- Connected-person payments **> AED 500k** → Connected Persons schedule.
- Net interest (current + carried-forward) **> AED 12M** → Interest Capping schedule.
- Downward TP adjustments require **prior FTA approval**.
- Prior-period error with CT impact **≤ AED 10k** corrected in-return; larger → Voluntary Disclosure.

## 13. Document retention, assessment, audit, voluntary disclosure

- **Retention:** records supporting the return kept **7 years**; audited FS where revenue > AED 50M and for all QFZPs (MD 82/2023). Basis Art. 56 (+ Tax Procedures Law FDL 28/2022, ER Cabinet Decision 74/2023). ⚠️ VERIFY exact years / 48-hour production rule.
- **Self-assessment;** FTA may issue a **Tax Assessment** and conduct **risk-based audits** (advisory sources note a 2026 shift to risk-based CT audits).
- **Voluntary Disclosure** (Art. 10 FDL 28/2022): required for prior-period errors with CT impact **> AED 10k**.
- **Clarifications:** private FTA rulings via EmaraTax.
- ⚠️ VERIFY objection window (commonly cited 40 business days) and any 1 April 2026 Tax-Procedures amendments against the law.

## 14. Administrative penalties — Cabinet Decision No. 75 of 2023 (+ CD 10/2024)

⚠️ The primary MoF PDF was not machine-readable this pass; figures below are from a
practitioner reproduction and **must be verified line-by-line before hard-coding**.

| Violation | Penalty |
|-----------|---------|
| Late registration | **AED 10,000** |
| Failure to keep records | AED 10,000 (AED 20,000 if repeated within 24 months) |
| Late filing | AED 500/month (first 12 months); AED 1,000/month thereafter |
| Late payment | 14% per annum, applied monthly on the unpaid tax |
| Late deregistration | AED 1,000/month, capped at AED 10,000 |
| Incorrect return | AED 500 (waived if corrected before the deadline) |
| Voluntary disclosure | 1%/month on the tax difference; 15% fixed + 1%/month if after audit notice |

## 15. Terminology glossary (FTA definitions — CTGTXR1 §1)

Taxable Person (Art. 11) · Resident (11(3)) / Non-Resident (11(4)) · Exempt Person (Art. 4)
· Free Zone Person / **QFZP** (Art. 18, taxed under 3(2)) · Qualifying Income (CD 100/2023;
activities MD 265/2023 → MD 229/2025) · Tax Period (Art. 57) · **Accounting Income** (net
P&L per Art. 20; standards MD 114/2023) · **Taxable Income** (Art. 20, adjusted) ·
Corporate Tax Payable · Related Party (Art. 35) · Connected Person (Art. 36) · Tax Group
(Art. 40) · Participating Interest / Participation Exemption (Art. 23 + MD 116/2023) ·
Permanent Establishment / Foreign PE / Domestic PE (Art. 14) · Tax Loss (Art. 37–39) · Net
Interest Expenditure (Art. 30) · Foreign Tax Credit (Art. 47) · Withholding Tax (Arts. 45–46,
currently **0%**) · Voluntary Disclosure (Art. 10 FDL 28/2022) · Tax Agent / Legal
Representative · Unincorporated Partnership · **Revenue** (per tax period) vs **Turnover**
(per Gregorian year) · Market Value (arm's-length price).

## 16. Data-model implications (→ engine & schema)

The knowledge model drives these concrete needs, several of which extend today's
`app/ct/schemas.py`:
- **Elections** as first-class fields (SBR, realisation basis, transitional rules, FPE, qualifying-group, business-restructuring) with per-election irrevocability metadata.
- **Schedule-triggering** thresholds (AED 40M RP, AED 500k connected, AED 12M interest) as config, driving both validation and which schedules render.
- **Accounting-income → adjustments → taxable income → tax** as a traceable computation graph (Part D/F/G structure).
- **QFZP** date-effective activity lists (MD 265 vs MD 229) and the 5-period breach lockout.
- **Participation exemption** inputs (ownership %, cost, holding period, subject-to-tax) — not yet modelled in the engine.
- **Penalty** computation inputs (dates → late-reg/filing/payment exposure).

See [ct-database-schema.md](ct-database-schema.md) for the persisted form.

## 17. Corrections & enhancements to apply to the built engine (`app/ct/`)

From this research, the following updates should be made to the step-1–3 engine (all
behind the provisional/SME gate):
1. **DMTT legal basis** → `FDL 60/2023 + Cabinet Decision 142/2024` (constants currently cite CD 142 only).
2. **Registration deadline map** → confirmed correct; no change.
3. **Penalty detail** → optionally expand beyond the AED 10k late-reg flag to late-filing / late-payment exposure (§14), once CD-75 figures are verified.
4. **TP rule** → add the **return-disclosure thresholds** (AED 40M RP / AED 500k connected) distinct from the master/local-file thresholds (AED 200M / 3.15bn) the engine already uses.
5. **Free Zone activities** → make the qualifying/excluded lists **date-effective** (MD 265/2023 vs MD 229/2025).
6. **New rules to add:** participation-exemption condition check (Art. 23), interest **carryforward** tracking, realisation-basis consistency, transitional-rules presence.
7. **Migrate `ct/constants.py`** into the versioned config engine so these become dated, cited config versions rather than literals.

## 18. Legislation & guidance register

| Instrument | Topic | Link |
|-----------|-------|------|
| Federal Decree-Law No. 47 of 2022 | CT Law | [MoF PDF](https://mof.gov.ae/wp-content/uploads/2022/12/Federal-Decree-Law-No.-47-of-2022-EN.pdf) |
| Federal Decree-Law No. 60 of 2023 | Amends Art. 3 (enables DMTT) | MoF |
| Cabinet Decision No. 142 of 2024 | DMTT / Top-up Tax | [FTA PDF](https://tax.gov.ae/Datafolder/Files/Legislation/Cabinet-Decision-No-142-of-2024-on-Top-up-Tax-on-MNEs.pdf) |
| Cabinet Decision No. 49 of 2023 | Natural persons in scope | MoF |
| Cabinet Decision No. 100 of 2023 | Qualifying Income (Free Zone) | MoF |
| Cabinet Decision No. 75 of 2023 (+ CD 10/2024) | Administrative penalties | [MoF PDF](https://mof.gov.ae/wp-content/uploads/2024/03/Cabinet-Decision-No.-75-of-2023-and-its-amendments-on-the-Administrative-Penalties-for-Violations-Related-to-the-Application-of-Federal-Decree-Law-No.-47-of-2022.pdf) |
| FTA Decision No. 3 of 2024 | Registration timelines | [FTA PDF](https://tax.gov.ae/Datafolder/Files/Legislation/FTA%20Decision%20No.%203%20of%202024%20on%20Registration%20Timeline%20for%20Corporate%20Tax%20-%20For%20publishing.pdf) |
| Ministerial Decision No. 73 of 2023 | Small Business Relief | MoF |
| Ministerial Decision No. 82 of 2023 | Audited FS requirement | MoF |
| Ministerial Decision No. 97 of 2023 | Transfer pricing documentation | [PwC PDF](https://www.pwc.com/m1/en/tax/documents/2023/uae-ct-ministerial-decision-no-97-2023.pdf) |
| Ministerial Decision No. 114 of 2023 | Accounting standards | MoF |
| Ministerial Decision No. 116 of 2023 | Participation exemption | MoF |
| Ministerial Decision No. 120 of 2023 | Transitional rules | MoF |
| Ministerial Decision No. 126 of 2023 | Interest deduction limitation | [MoF PDF](https://mof.gov.ae/wp-content/uploads/2023/05/Ministerial-Decision-No.-126-of-2023-on-the-General-Interest-Deduction-Limitation-Rule-for-the-Purposes-of-Federal-Decree-Law-No.-47-of-2022.pdf) |
| Ministerial Decision No. 132 of 2023 | Qualifying Group transfers | MoF |
| Ministerial Decision No. 133 of 2023 | Business Restructuring Relief | MoF |
| Ministerial Decision No. 134 of 2023 | General rules for taxable income | [MoF PDF](https://mof.gov.ae/wp-content/uploads/2023/05/Ministerial-Decision-No.-134-of-2023-on-the-on-the-General-Rules-for-Determining-Taxable-Income-for-Corporate-Tax-Purposes.pdf) |
| Ministerial Decision No. 265 of 2023 | Qualifying / Excluded Activities | [MoF PDF](https://mof.gov.ae/wp-content/uploads/2023/11/27.10.23-EN-Ministerial-Decision-No-265-of-2023-Regarding-Qualifying-Activities-and-Excluded-Activities.pdf) |
| Ministerial Decision No. 229 of 2025 | Qualifying / Excluded Activities (supersedes 265) ⚠️ | [MoF PDF](https://mof.gov.ae/wp-content/uploads/2025/09/EN-Ministerial-Decision-No.-229-of-2025-Regarding-Qualifying-Activities-and-Excluded-Activities.pdf) |
| FTA Guide **CTGTXR1** (Nov 2024) | The CT Return, field-by-field | [FTA PDF](https://tax.gov.ae/Datafolder/Files/Guides/CT/CT-Returns-EN-11-11-2024.pdf) |
| Tax Procedures Law — FDL 28 of 2022 (+ CD 74/2023) | Assessment, audit, VD, retention | MoF |

## 19. Knowledge-base ingestion plan (for the RAG corpus)

Ingest the PDFs in §18 into the knowledge base under **`category="corporate_tax"`**, via
the existing controlled *ingest → version → approve* pipeline (no scraping of tax.gov.ae).
The CT assistant then answers from retrieved official text, regime-filtered to CT — same
honesty stance as the VAT KB.

## 20. Verification backlog

Must clear with a CT SME / against the gazette **before the corresponding rule is trusted**:

| # | Item | Why flagged |
|---|------|-------------|
| 1 | Art. 33 non-deductible itemisation | Partly from secondary commentary |
| 2 | CD-75/2023 penalty figures (late filing/payment, VD %) | Primary PDF was 403; practitioner reproduction |
| 3 | MD 229/2025 supersession scope + exact effective date | New instrument; confirm cutover vs MD 265 |
| 4 | QFZP audited-FS MD number (84/2025?) | Attributed via commentary |
| 5 | Retention years / 48-hour production / 2026 Tax-Procedures amendments | Advisory sources, not tax.gov.ae |
| 6 | Objection window (40 business days) & VD penalty rate | Advisory sources |
| 7 | TP disclosure thresholds (AED 40M / 4M / 500k) | From FTA guidance/commentary — confirm vs CTGTXR1 |
| 8 | All CT-Law article numbers (20, 23, 24, 26–40, 47, 53, 56–58, 69) | Consistent across sources but not each re-verified line-by-line vs the Decree-Law PDF |

Clearing this backlog is the gate the `app/ct` engine's PROVISIONAL markers refer to.
