# UAE Corporate Tax Module — Delivery Roadmap

This is a **program of work**, not a single build. It sequences the CT module into
shippable phases, each independently testable, and maps every one of the 16 requested
deliverables to where it lands. It builds on what already exists rather than restarting.

---

## Current status (already built & verified)

| Done | Evidence |
|------|----------|
| Regime-agnostic compliance core + `Regime` discriminator | `app/compliance/`, `regime` column on Document/Review — 65 tests green |
| CT domain schema (`CorporateTaxReturn`, entity/period model) | `app/ct/schemas.py` |
| CT deterministic rule engine — 15 rules (provisional citations) | `app/ct/rules.py`, `tests/test_ct_rules.py` (19 tests) |
| CT validation (gaps → verification, not failures) | `app/ct/validation.py` |
| Authoritative knowledge foundation | [ct-knowledge-model.md](ct-knowledge-model.md), [ct-compliance-brief.md](ct-compliance-brief.md) |
| Architecture + normalized DB schema | [ct-architecture.md](ct-architecture.md), [ct-database-schema.md](ct-database-schema.md) |

**⚠️ Gating dependency:** the rule set and all legal references are **PROVISIONAL** until
validated by a UAE CT subject-matter expert (enforced by a test that checks every
`legal_ref` carries the marker). SME sign-off on [ct-knowledge-model.md](ct-knowledge-model.md)
should precede trusting any verdict in a real FTA context.

### Build log — 2026-08-06 (Phase B + Phase C core + §17 fixes)
- **§17 engine corrections applied:** DMTT basis now cites FDL 60/2023 + CD 142/2024; added return-disclosure TP thresholds (AED 40M / 500k) as a new rule **CT-TP-002** distinct from the master/local-file thresholds; added **CT-EXM-001** participation-exemption condition check; Free Zone activity ref made date-effective (MD 265/2023 → MD 229/2025).
- **Phase C core — calculation engine** (`app/ct/computation.py`): traceable profit→tax computation graph (accounting profit ± adjustments → taxable income → loss relief ≤75% → 0%/9% bands → FTC → CT payable), each step a `ComputationLine` with legal ref. Wired into `review_ct_return` (result now carries a full `computation`).
- **Phase B — persistence + API:** `ct_returns` table (`CtReturnRecord`); `app/ct/service.py`; `app/api/routes_ct.py` mounted at `/api/ct/*` — create/list/get/patch/validate/compute/status/dashboard/delete. 17 rules now; **80 tests green** (33 CT-specific).
- **Deferred (later Phase C/D):** trial-balance/GL import + CoA→tax-line mapping, the full 20-schedule detail, the versioned config engine (constants still literal), and the real workflow state machine (status endpoint is a simple setter for now).

### Build log — 2026-08-06 (Phase F — dashboard UI)
- **`/corporate-tax` page** (`apps/web/app/corporate-tax/page.tsx`): executive dashboard tiles (returns, pending, high-risk, total CT payable) + upcoming filing deadlines; a new-return form (core fields + collapsible adjustments / free-zone / TP / participation inputs); the result view — compliance/risk badges, taxable-income / CT-payable / effective-rate tiles, workflow-status selector, the full **tax computation trace** (each line with legal ref), findings, and verification items; plus a saved-returns table with load/delete.
- Added CT types + API client methods (`lib/types.ts`, `lib/api.ts`) and a "Corporate Tax" nav entry (`components/app-shell.tsx`).
- Verified: `tsc --noEmit` clean; **live E2E** through the running app (login → create 2 returns → dashboard aggregates → load → computation trace renders). Frontend must run on **:3000** (backend CORS `allow_origins`).

---

## Phases

### Phase A — Foundation & knowledge (mostly done)
Research, knowledge model, architecture, DB schema, the regime core, and the first
deterministic rule/validation pass. **Remaining:** SME validation of the knowledge model;
migrate `ct/constants.py` into the versioned **config engine** (`compliance/config/`).

### Phase B — Persistence & API skeleton
Build the CT tables (§ [ct-database-schema.md](ct-database-schema.md)) via Alembic; add
`routes_ct.py` (create/list/get/update returns, dashboard aggregates); wire
`review_ct_return` behind `POST /api/ct/returns/{id}/validate`. **Exit:** you can create a
CT return over the API and get classified findings back.

### Phase C — Data ingestion & Calculation Engine
Trial-balance / GL import (reuse the `vat201` generic importer pattern); Chart-of-Accounts
→ tax-line **mapping**; the **calculation engine** (`ct/computation.py`) producing a
traceable profit→tax computation graph; supporting **schedules** (depreciation, losses,
adjustments, exempt income, disallowed expenses). **Exit:** import a TB → computed taxable
income + CT payable with a full audit trace.

### Phase D — Workflow, approvals, audit, notifications
The 10-state **workflow engine** with RBAC-gated transitions and multi-level approvals;
the append-only **audit engine**; the **notification service** (filing-deadline and task
alerts). **Exit:** a return moves Draft → … → Filed with full history and approvals.

### Phase E — Reporting
The full report set (Tax Computation, Adjustment Schedule, TB Mapping, Related-Party, TP
Summary, Tax-Loss, Group Relief, Filing-Readiness, Executive, Audit, Exception) to
PDF/Excel/CSV/JSON, reusing the existing reportlab/openpyxl toolchain.

### Phase F — Dashboard & workspace UI (Next.js)
Executive dashboard (KPIs, charts, filters, drill-down) + the return workspace (data
entry, mapping grid, findings, computation view, workflow controls, report downloads).

### Phase G — AI compliance assistant
CT extraction method on the AI provider (financials → `CorporateTaxReturn`); CT RAG corpus
(`category='corporate_tax'`) + regime-filtered retrieval; explainable advisory
(explain-errors, suggest-adjustments, missing-docs, anomaly-flags, filing-readiness
prediction) — all as **proposals**, never auto-applied.

### Phase H — Hardening
RBAC depth, document encryption, performance (async compute/reports, indexing, caching,
pagination), security review, and deployment docs.

---

## Deliverable → phase map

| # | Requested deliverable | Lands in | Status |
|---|-----------------------|----------|--------|
| 1 | System architecture | A | ✅ [ct-architecture.md](ct-architecture.md) |
| 2 | Database schema | A/B | ✅ designed → build in B |
| 3 | Backend services | B–E | ◑ rule/validation/computation/persistence services done |
| 4 | REST/GraphQL APIs | B | ✅ `/api/ct/*` (REST) |
| 5 | Business rules engine | A/B | ◑ rules exist → still to move to versioned config |
| 6 | CT calculation engine | C | ✅ core done (`ct/computation.py`); TB import/CoA mapping pending |
| 7 | Validation engine | A | ✅ |
| 8 | Dashboard UI | F | ✅ `/corporate-tax` page (dashboard + return workspace) |
| 9 | Reporting module | E | ⏳ |
| 10 | Audit module | D | ⏳ |
| 11 | Workflow engine | D | ⏳ |
| 12 | AI compliance assistant | G | ⏳ |
| 13 | Technical documentation | all | ◑ ongoing |
| 14 | Database documentation | A/B | ✅ [ct-database-schema.md](ct-database-schema.md) |
| 15 | API documentation | B | ⏳ (OpenAPI auto + guide) |
| 16 | Deployment documentation | H | ◑ base exists ([DEPLOYMENT.md](DEPLOYMENT.md)) |

✅ done · ◑ partial · ⏳ planned.

---

## Recommended next build step

**Phase B, first slice:** persist CT returns and expose `POST /api/ct/returns` +
`/validate` so the existing 15-rule engine is callable end-to-end over the API and from
the UI. It's the smallest increment that turns the engine into a usable feature and
unblocks the dashboard. This does **not** require SME sign-off (verdicts stay marked
provisional) — but trusting the output in production does.
