# UAE Corporate Tax Module — System Architecture

Enterprise-grade, modular, configurable, audit-ready design for the UAE Corporate Tax
(CT) compliance module. It **extends the existing platform** (FastAPI + Next.js +
Postgres/pgvector) rather than replacing it, reusing the regime-agnostic compliance
core introduced in `app/compliance/` and following the proven `app/vat/` + `app/vat201/`
patterns.

**Companion docs:** [ct-knowledge-model.md](ct-knowledge-model.md) (the authoritative
domain foundation), [ct-database-schema.md](ct-database-schema.md) (normalized schema),
[ct-roadmap.md](ct-roadmap.md) (phased delivery + deliverable mapping),
[ct-compliance-brief.md](ct-compliance-brief.md) (rate/threshold reference),
[ct-readiness-audit.md](ct-readiness-audit.md) (how the codebase generalizes).

---

## 1. Guiding principles

1. **Trust before cleverness.** Every tax verdict and calculation comes from a
   **deterministic, traceable engine** — never from a language model. The AI layer
   assists (extraction, explanation, risk-spotting, drafting) but **never adjudicates or
   auto-changes a figure**. This is the platform's founding principle and it is
   non-negotiable for an FTA-audit-defensible tool.
2. **Every rule and rate is data, not code.** Rates, thresholds, deadlines, account
   mappings, adjustment definitions, validation rules, and workflow transitions live in
   **versioned configuration** so a legislative change is a config edit + new version,
   not a redeploy. Each config version is date-effective and cited to its legal source.
3. **Traceability end-to-end.** Every computed number carries a computation trace (inputs
   → rule → output → legal reference). Every state change is journaled. Nothing is lost.
4. **Reuse, don't fork.** CT is a *second regime* on shared infrastructure: the
   `Regime` discriminator, `Finding`/`ReviewResultBase` primitives, RAG/knowledge layer,
   auth, object storage, and report pipeline are all shared with VAT.
5. **Configurable, not hardcoded.** Business rules, schedules, and workflows are
   declarative and org-overridable.

---

## 2. Where CT sits in the monorepo

```
apps/
├─ api/  (FastAPI)
│  └─ app/
│     ├─ compliance/     [SHARED] regime-agnostic primitives + verdict logic   ✅ exists
│     │     domain.py    Finding, ReviewResultBase, Severity, Regime, status_and_risk
│     │     config/      [NEW] versioned rule/rate/mapping config loader
│     ├─ vat/            VAT regime (invoice-level)                             ✅ exists
│     ├─ vat201/         VAT return generator                                   ✅ exists
│     ├─ ct/             CORPORATE TAX regime                                   ◑ steps 1-3 done
│     │     schemas.py       CorporateTaxReturn + CT enums + CTReviewResult     ✅
│     │     constants.py     rates/thresholds/legal-refs (→ migrate to config)  ✅
│     │     validation.py    verification + data-integrity checks               ✅
│     │     rules.py         deterministic compliance rules (15, provisional)   ✅
│     │     computation.py   [NEW] tax computation engine (profit→tax)
│     │     schedules.py     [NEW] supporting schedules (depreciation, losses…)
│     │     mapping.py       [NEW] trial-balance / CoA → tax line mapping
│     │     workflow.py      [NEW] state machine (10 states)
│     │     report.py        [NEW] CT report builders (PDF/Excel/CSV/JSON)
│     │     extraction.py    [NEW] financials → CorporateTaxReturn (AI-assisted)
│     ├─ ai/             [SHARED] provider-agnostic layer (+ CT prompts/methods)
│     ├─ rag/            [SHARED] knowledge base (+ CT corpus, regime-filtered)
│     ├─ audit/          [NEW/SHARED] immutable audit trail service
│     ├─ notifications/  [NEW/SHARED] deadline & task notification service
│     ├─ auth/           [SHARED] JWT + RBAC (extend roles/permissions)
│     └─ api/            routes — add routes_ct.py, routes_ct_workflow.py, …
└─ web/  (Next.js)
   └─ app/
      ├─ (vat pages …)                                                          ✅ exists
      └─ ct/            [NEW] dashboard, return workspace, schedules, reports, workflow
```

Legend: ✅ built · ◑ partially built (CT steps 1–3) · **[NEW]** to build.

---

## 3. Layered architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION   Next.js CT dashboard · return workspace · schedules · reports│
├──────────────────────────────────────────────────────────────────────────┤
│ API            FastAPI REST (/api/ct/*) · OpenAPI · auth-gated · RBAC       │
├──────────────────────────────────────────────────────────────────────────┤
│ APPLICATION / ORCHESTRATION   services that compose engines per request     │
├───────────┬───────────┬───────────┬───────────┬───────────┬────────────────┤
│ Calculation│ Validation│ Workflow  │ Reporting │ Audit     │ AI Assistant   │
│ Engine     │ Engine    │ Engine    │ Engine    │ Engine    │ (explainable)  │
├───────────┴───────────┴───────────┴───────────┴───────────┴────────────────┤
│ BUSINESS RULES   versioned, date-effective config (rates, rules, mappings)  │
├──────────────────────────────────────────────────────────────────────────┤
│ DOMAIN           CorporateTaxReturn, schedules, computation-trace models     │
├──────────────────────────────────────────────────────────────────────────┤
│ PERSISTENCE      SQLAlchemy ORM · Postgres (+pgvector) · object storage      │
├──────────────────────────────────────────────────────────────────────────┤
│ CROSS-CUTTING    Security · Notifications · Caching · Async jobs · Logging   │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Business Rules layer (the configurability backbone)
A `app/compliance/config/` package loads **versioned rule sets** from
JSON/YAML (seeded in DB, overridable per org):

- `rates_ct@<version>` — bands, thresholds, DMTT, effective-from date, legal ref.
- `adjustments_ct@<version>` — catalogue of permanent/temporary differences, each with
  id, label, sign, deductibility %, legal ref, and the input it consumes.
- `validations_ct@<version>` — declarative checks (field, predicate, severity, message,
  recommendation, legal ref).
- `coa_map@<org>` — trial-balance/chart-of-accounts → tax-line mapping.
- `workflow_ct@<org>` — states, allowed transitions, required role, entry gates.

Each version is **date-effective** and **cited**. The engines read config; they contain
no literal rates. (Today's `ct/constants.py` is the seed for `rates_ct@v1` /
`adjustments_ct@v1`.)

### 3.2 Calculation Engine (`ct/computation.py`)
Deterministic profit→tax pipeline producing a **computation graph** (every node = inputs,
rule id, formula, output, legal ref):

```
Accounting net profit (IFRS)
  ± Permanent differences        (exempt income, non-deductibles, entertainment 50%)
  ± Temporary differences        (tax vs accounting depreciation, provisions, …)
  = Adjusted taxable income (pre-relief)
  − Tax loss offset (≤75%)       → Taxable income
  Apply bands: 0% ≤ 375,000; 9% above   (QFZP 0% on qualifying; SBR → nil)
  − Foreign tax credit
  = Corporate Tax Payable
```
Output is a `CTComputation` object: ordered line items + total + a serialisable trace,
persisted immutably per return version. Heavy computations run **async** (job queue).

### 3.3 Validation Engine (`ct/validation.py`, config-driven)
Runs declarative checks → `Finding`/`VerificationItem`/`ValidationCheck` with severities
mapped to **Critical / High / Medium / Low / Information**. Missing data → verification
item (never an automatic fail). Each finding carries a corrective recommendation + legal
ref. Categories: missing data, account-mapping errors, invalid adjustments, related-party
/ TP gaps, wrong tax period, duplicates, filing-readiness, maths inconsistencies, missing
approvals, required declarations.

### 3.4 Workflow Engine (`ct/workflow.py`)
Config-driven state machine over the 10 states: **Draft → Data Collection → Validation →
Internal Review → Tax Review → Management Approval → Ready for Filing → Filed → Under FTA
Review → Closed.** Each transition records actor, timestamp, from/to, note; gated by RBAC
role and entry conditions (e.g. "no Critical findings open" before *Ready for Filing*).

### 3.5 Reporting Engine (`ct/report.py`)
Renders the report set (Tax Computation, Adjustment Schedule, Trial-Balance Mapping,
Related-Party, TP Summary, Tax-Loss Schedule, Group Relief, Filing-Readiness, Executive
Summary, Audit, Exception) to **PDF / Excel / CSV / JSON**, reusing the existing
`reportlab` + `openpyxl` toolchain. Every report is a projection of persisted immutable
data, so it is reproducible for any return version.

### 3.6 Audit Engine (`app/audit/`)
Append-only `audit_events` (actor, action, entity, before/after JSON, timestamp, request
id). Every write path emits an event; the return keeps immutable **version snapshots**
(like `Review.*_json` today). Nothing is destructively overwritten.

### 3.7 AI Assistant (explainable, grounded, non-authoritative)
Provider-agnostic (`app/ai/`, Claude default). Roles: extract financials →
`CorporateTaxReturn`; explain validation errors in plain language; suggest likely
adjustments and missing documents; flag anomalies/unusual transactions; predict filing
readiness. **Constraints:** every suggestion is a *proposal* the user accepts/rejects;
AI never mutates a figure or verdict; outputs cite retrieved authoritative text via the
RAG layer (regime-filtered to CT). With no API key, deterministic data-grounded
fallbacks apply (same as VAT).

---

## 4. API surface (REST, `/api/ct/*`)

Mirrors existing conventions (auth-gated, OpenAPI at `/docs`). Illustrative:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/ct/returns` | Create a CT return (entity + tax period) |
| GET  | `/api/ct/returns` | List (filter by status, period, risk) |
| GET  | `/api/ct/returns/{id}` | Full return + findings + computation trace |
| PATCH| `/api/ct/returns/{id}` | Update return data (draft) |
| POST | `/api/ct/returns/{id}/import` | Import trial balance / GL (CSV/Excel) |
| POST | `/api/ct/returns/{id}/compute` | Run calculation engine → computation + trace |
| POST | `/api/ct/returns/{id}/validate` | Run validation engine → classified findings |
| POST | `/api/ct/returns/{id}/transition` | Advance workflow state (RBAC-gated) |
| GET  | `/api/ct/returns/{id}/report?type=&format=` | Generate a report (pdf/xlsx/csv/json) |
| GET  | `/api/ct/returns/{id}/audit` | Audit trail for the return |
| GET  | `/api/ct/dashboard` | Executive KPIs / aggregates |
| POST | `/api/ct/ai/analyze/{id}` | AI advisory (explainable, cited) |
| GET  | `/api/ct/config/{name}` | Active versioned rule/rate/mapping set |
| CRUD | `/api/ct/related-parties`, `/api/ct/documents`, … | Supporting entities |

GraphQL is optional; REST is the default to stay consistent with the current API.

---

## 5. Security layer

Builds on the existing JWT auth (`app/auth/`). Additions:
- **RBAC** roles for CT: `preparer`, `tax_reviewer`, `approver`, `admin`, `viewer`,
  mapped to workflow-transition permissions.
- **Multi-level approvals** enforced by the workflow engine (Tax Review → Management
  Approval).
- **Audit logs** (§3.6), **version history** on returns, **document encryption** at rest
  in object storage, secure API auth, session management, activity monitoring.
- Row-level scoping by company/tenant for multi-entity groups.

---

## 6. Performance

- Postgres indexing on `regime`, `company_id`, `tax_period_id`, `status`, and FKs.
- **Async** for the calculation engine, report generation, and AI calls (job queue;
  Celery/Redis already in the stack).
- **Caching** of active config versions and dashboard aggregates.
- **Lazy loading** / pagination on GL and trial-balance grids (can be 100k+ rows).
- Bulk import streamed and validated in batches.

---

## 7. What already exists vs. what's new

| Capability | Status |
|------------|--------|
| Regime-agnostic primitives + `Regime` discriminator | ✅ done (steps 1–2) |
| CT domain schema + 15 provisional rules + validation | ✅ done (step 3) |
| Shared auth, object storage, RAG, report toolchain (reportlab/openpyxl) | ✅ exists (VAT) |
| Versioned config engine, calculation engine, schedules, CoA mapping | **new** |
| Workflow engine, audit engine, notifications | **new** |
| CT API routes, CT dashboard + workspace UI, CT report set | **new** |
| CT AI extraction/advisory methods + CT RAG corpus | **new** |

The phased plan to build the "new" rows — and the mapping to your 16 deliverables — is in
[ct-roadmap.md](ct-roadmap.md).
