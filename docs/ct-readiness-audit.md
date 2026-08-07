# CT-Readiness Audit — Extending the Platform to Corporate Tax

An honest assessment of how well the current **VAT** codebase (`apps/api`) would
generalize to a **second tax regime (UAE Corporate Tax)**, and a concrete plan to get
there. Companion to [ct-compliance-brief.md](ct-compliance-brief.md) (the domain content).

**Verdict up front:** the platform is a **well-layered single-regime application, not a
multi-regime framework**. The compliance *primitives* and the *entire knowledge/RAG and
file-acquisition layers* are genuinely regime-agnostic and reusable. The domain model,
rule bodies, structured extractor, and persistence are hardcoded to VAT. There is **no
`regime`/`tax_type` discriminator anywhere** — VAT is the implicit and only regime.

---

## Layer-by-layer readiness

| Layer | Key files | Reusable for CT? |
|-------|-----------|------------------|
| Compliance primitives — `Finding`, `ReviewResult`, `ValidationCheck`, `VerificationItem`, `Severity`, `ComplianceStatus`, `RiskLevel`, `Party` | `app/vat/schemas.py:44-66,142-184` | ✅ **As-is** — no VAT fields; just need to move out of the `vat/` package |
| Rule-engine *pattern* (fn-list → run in sequence → severity→verdict) | `app/vat/rules.py:279-315` | ✅ **Pattern reusable**; rule *bodies* are VAT-specific |
| Knowledge base schema + RAG ingest/retrieve | `app/models.py:137-169`, `app/rag/store.py` | ✅ **As-is** (columns are generic: title/source_ref/category/text/embedding) |
| File acquisition / OCR / text extraction | `app/services/extraction.py:83-98`, `app/services/ocr.py` | ✅ **As-is** — format handling is content-agnostic |
| Review persistence (JSON blobs + status columns) | `app/models.py:53-91` | 🟡 **Mostly** — blobs are schema-flexible, but no regime discriminator; `doc_type` is VAT-typed |
| AI provider Protocol + prompts | `app/ai/base.py:41-59`, `app/ai/prompts.py` | 🟡 **Swappable Protocol**, but persona + `extract_invoice()->Invoice` are VAT-hardcoded |
| `Invoice` domain model + enums | `app/vat/schemas.py:17-138` | ❌ **VAT-only** — CT is not invoice-shaped |
| Rule bodies / constants / legal refs | `app/vat/rules.py:64-273`, `app/vat/constants.py` | ❌ **VAT-only** |
| Structured extraction (offline parser) | `app/services/field_extraction.py` (~500 lines) | ❌ **VAT-only** (TRN regex, net+VAT=gross solver) |
| VAT-201 return module | `app/vat201/*`, `app/models.py:94-134` | ❌ **VAT-only** — but a **good structural template** (see below) |
| Routes / dispatch | `app/api/*`, `app/main.py:93-96` | 🟡 **Single-regime** — no `regime` path segment or param |
| Config constants | `app/core/config.py:42-46` | ❌ hardcodes VAT rate/thresholds; no second-regime params |

---

## The key structural mismatch

VAT review is **transactional** — one `Invoice` in, findings out. CT review is
**entity- and period-level** — a full annual computation from financial statements. You
**cannot** shoehorn a CT return into the `Invoice` model (`schemas.py:97-138`), and you
shouldn't try. CT needs its own `CorporateTaxReturn` schema (entity → tax period →
financial-statement figures → adjustments), a different extraction target, and a
different review flow. What it can *share* is everything downstream of the domain object:
the finding primitives, verdict derivation, persistence blobs, RAG, and file acquisition.

The existing **`app/vat201/`** package is the best model to copy: it's a self-contained
sibling sub-domain with its own schemas + engine + routes + models. A new **`app/ct/`**
package following that shape is the natural home for CT.

---

## Recommended path (in dependency order)

**1. Promote the generic primitives out of `vat/`.**
Move `Finding`, `ReviewResult`, `ValidationCheck`, `VerificationItem`, `Severity`,
`ComplianceStatus`, `RiskLevel`, `Party` from `app/vat/schemas.py` into a shared
`app/compliance/domain.py` (or `app/core/domain.py`). Re-export from `vat.schemas` so
nothing breaks. This is a pure refactor with no behaviour change — do it first.

**2. Add a `regime` discriminator.**
Introduce a `Regime` enum (`VAT | CT`) and add a `regime` column to `Document` and
`Review` (`models.py:47,53-91`). Default existing rows to `VAT` in a migration. This is
the one change that unblocks everything multi-regime.

**3. Build the `app/ct/` package.**
`ct/schemas.py` (`CorporateTaxReturn` + CT enums), `ct/rules.py` (the catalogue sketched
in the brief — CT-REG-*, CT-SBR-*, CT-RATE-*, CT-FZ-*, CT-INT-*, …), `ct/constants.py`
(rates 0%/9%, AED 375k / 3M / 5M / 12M / 50M thresholds, sunset 31 Dec 2026, `legal_ref`
map to Decree-Law 47/2022). Reuse the primitives from step 1.

**4. CT extraction.**
Add `extract_return()` (or a CT-specific method) to the `AIProvider` Protocol
(`ai/base.py`) and a CT prompt persona (`ai/prompts.py`). The **file-acquisition/OCR
layer needs no changes** — only the structured mapping is new.

**5. Dispatch on regime.**
Turn `process_upload` (`services/review_service.py:18-67`) into a dispatcher keyed on
`Document.regime`. Either namespace routes (`/api/vat/...` + `/api/ct/...`) or add a
`regime` param to the upload endpoint. Keep the legacy `POST /api/review`
(`main.py:93-96`) as a VAT alias.

**6. Multi-regime RAG.**
`rag/store.retrieve()` (`store.py:80-105`) does **not** currently filter by category, so
a CT question would retrieve VAT chunks. Add a `category`/`regime` filter, seed a CT
corpus (`category="corporate_tax"`) alongside the 13 VAT entries in `rag/seed.py`, and
scope the chat assistant to the active regime.

---

## Effort & risk

- **Steps 1–2** (refactor + discriminator): low risk, high leverage — do them regardless.
- **Step 3** (CT rules): the real domain work; gated on SME validation of
  [ct-compliance-brief.md](ct-compliance-brief.md), exactly as the VAT rule catalogue was.
- **Steps 4–6**: mechanical once the schema exists.
- **Biggest risk** is **not** architectural — it's **legal accuracy**. Every `legal_ref`
  in the CT rule set must be confirmed against the official gazette before the engine's
  verdicts are trusted, per the platform's "trust before cleverness" principle.

---

## What I did *not* change

This is an assessment only — **no code was modified**. All file:line references above are
observations of the current tree.
