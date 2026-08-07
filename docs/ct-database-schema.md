# UAE Corporate Tax Module — Database Schema

Normalized, scalable schema for the CT module. Follows the existing platform's ORM
conventions (SQLAlchemy 2.0 `Mapped[...]`, 32-char UUID string PKs, `regime`
discriminator, JSON snapshots for immutable records, timezone-aware timestamps). Targets
Postgres in production, SQLite in dev — same as the rest of the app.

**Conventions**
- PK `id`: `String(32)` UUID hex. FKs named `<entity>_id`.
- Every business table carries `created_at`, `updated_at`; mutable business records also
  carry `created_by`, `updated_by` (FK → `users`).
- Money stored as `Numeric(18,2)` (AED). Dates as `Date`; instants as `DateTime(tz)`.
- Multi-entity ready: most tables carry `company_id`; group-level tables carry
  `tax_group_id`.
- Immutable snapshots (computations, filed returns, audit) are never updated in place.

Legend for "Status": ✅ exists today · **NEW** to add.

---

## A. Organization & registration

| Table | Key columns | Notes | Status |
|-------|-------------|-------|--------|
| `companies` | id, legal_name, trade_name, license_no, license_issue_date, license_issue_month, incorporation_date, emirate, legal_form, is_free_zone, free_zone_name, taxpayer_type | The taxable entity (juridical/natural/non-resident) | NEW |
| `tax_registrations` | id, company_id→companies, regime (vat\|ct), trn, registration_date, registration_deadline, status, effective_from | One row per regime per company; drives registration findings | NEW |
| `users` | id, email, password_hash, full_name, role, is_active | RBAC principal | ✅ |
| `company_users` | id, company_id, user_id, role | Per-company role scoping (multi-tenant) | NEW |

## B. Periods

| Table | Key columns | Notes |
|-------|-------------|-------|
| `financial_periods` | id, company_id, start_date, end_date, label, accounting_standard (ifrs\|ifrs_sme) | The accounting year |
| `ct_tax_periods` | id, company_id, financial_period_id, start_date, end_date, is_first_period, filing_due_date, payment_due_date, status | The CT tax period; deadlines derived here |

## C. Financial data (ledger source)

| Table | Key columns | Notes |
|-------|-------------|-------|
| `chart_of_accounts` | id, company_id, code, name, type (asset\|liability\|equity\|income\|expense), parent_id, tax_line_code | CoA with a mapping hook to tax lines |
| `trial_balances` | id, company_id, tax_period_id, source_filename, imported_at, status | A TB import batch |
| `trial_balance_lines` | id, trial_balance_id, account_code, account_name, debit, credit, mapped_tax_line | Indexed by (trial_balance_id, account_code) |
| `general_ledger_entries` | id, company_id, tax_period_id, account_code, date, description, debit, credit, journal_id, related_party_id | Optional GL detail; partitioned/paginated |
| `journal_entries` | id, company_id, tax_period_id, ref, date, memo, created_by, status | Header for manual/adjusting entries |
| `journal_entry_lines` | id, journal_entry_id, account_code, debit, credit | Balanced lines |
| `financial_statements` | id, company_id, tax_period_id, type (is\|bs\|cf), data_json, is_audited, source | Snapshot of FS figures used |

## D. Tax computation

| Table | Key columns | Notes |
|-------|-------------|-------|
| `ct_returns` | id, company_id, tax_period_id, regime='ct', status (workflow state), free_zone_status, is_mne_group_member, elects_sbr, elects_realisation_basis, foreign_pe_exemption, currency, return_json (immutable snapshot), compliance_status, risk_level, compliance_score, risk_score, submitted_at, filed_at, version | The central entity; mirrors `reviews` design |
| `ct_computations` | id, ct_return_id, version, accounting_profit, taxable_income_pre_relief, loss_offset, taxable_income, tax_before_credits, foreign_tax_credit, ct_payable, effective_rate, trace_json (immutable graph), computed_at, computed_by | Immutable per compute run |
| `tax_adjustments` | id, ct_return_id, adjustment_code (→ config), category (permanent\|temporary), label, direction (addback\|deduction), amount, account_ref, legal_ref, source (manual\|ai_suggested\|mapped), status | The adjustment schedule rows |
| `temporary_differences` | id, ct_return_id, description, book_value, tax_value, difference, origination_period, reversal_period | Deferred-tax tracking |
| `permanent_differences` | id, ct_return_id, description, amount, adjustment_code | Never reverse |
| `depreciation_adjustments` | id, ct_return_id, asset_class, accounting_depreciation, tax_depreciation, adjustment | Tax vs book depreciation |
| `exempt_income_items` | id, ct_return_id, type (dividend\|participation\|foreign_pe), amount, meets_conditions, legal_ref | Feeds permanent differences |
| `disallowed_expenses` | id, ct_return_id, type (entertainment\|fines\|donations\|interest_excess\|…), gross_amount, disallowed_amount, rule_ref | e.g. entertainment 50% |
| `capital_gains` | id, ct_return_id, asset, proceeds, base_cost, gain, treatment | Capital gains/losses |
| `foreign_tax_credits` | id, ct_return_id, country, foreign_income, foreign_tax_paid, credit_claimed, cap | FTC schedule |

## E. Losses, groups, free zone, reliefs

| Table | Key columns | Notes |
|-------|-------------|-------|
| `tax_losses` | id, company_id, origin_tax_period_id, amount, utilised, transferred, balance_cf, continuity_ok | Loss carryforward register |
| `tax_loss_utilisations` | id, tax_loss_id, ct_return_id, amount, cap_75pct_applied | Offset applications |
| `tax_groups` | id, parent_company_id, name, formed_date, status | Art. 40 group |
| `tax_group_members` | id, tax_group_id, company_id, ownership_pct, joined_date, left_date | ≥95% condition tracked |
| `group_relief_transfers` | id, tax_group_id, from_company_id, to_company_id, tax_period_id, amount, type | Loss/relief transfers |
| `qfzp_assessments` | id, ct_return_id, qualifying_income, non_qualifying_revenue, total_revenue, de_minimis_cap, de_minimis_ok, adequate_substance, audited_fs, status | QFZP condition & de minimis check |
| `sbr_elections` | id, ct_return_id, revenue, eligible, elected, period_end | Small Business Relief |

## F. Related parties & transfer pricing

| Table | Key columns | Notes |
|-------|-------------|-------|
| `related_parties` | id, company_id, name, relationship_type, jurisdiction, trn | Related Parties register |
| `connected_persons` | id, company_id, name, role, jurisdiction | Connected Persons (owners/directors) |
| `related_party_transactions` | id, ct_return_id, related_party_id, category, amount, tp_method, arms_length_range, is_arms_length | Feeds TP disclosure |
| `transfer_pricing_docs` | id, ct_return_id, doc_type (master_file\|local_file\|cbcr\|disclosure), storage_key, threshold_met, status | TP documentation set |

## G. Filing, assessment, compliance

| Table | Key columns | Notes |
|-------|-------------|-------|
| `filing_history` | id, ct_return_id, filed_at, reference, channel (emaratax), payload_json, acknowledgement | Immutable filing record |
| `assessments` | id, ct_return_id, type (self\|fta), assessed_tax, penalties, interest, notes, status | FTA/self assessments |
| `penalties` | id, company_id, ct_return_id, type (late_reg\|late_file\|late_pay\|incorrect_return), amount, basis, incurred_date, status | Penalty register |
| `compliance_findings` | id, ct_return_id, rule_id, severity (critical\|high\|medium\|low\|info), category, title, detail, legal_ref, recommendation, status | Persisted validation findings |
| `compliance_status_history` | id, ct_return_id, compliance_score, risk_score, status, snapshot_at | Dashboard trend |

## H. Workflow, approvals, documents

| Table | Key columns | Notes |
|-------|-------------|-------|
| `workflow_transitions` | id, ct_return_id, from_state, to_state, actor_id, note, occurred_at | Full state history |
| `approvals` | id, ct_return_id, level (tax_review\|management), approver_id, decision, note, decided_at | Multi-level approval |
| `documents` | id, company_id, ct_return_id (nullable), regime, category, filename, mime, size_bytes, storage_key, encrypted, uploaded_by, uploaded_at | Supporting docs (shared table extends existing `documents`) |
| `document_requirements` | id, ct_return_id, requirement_code, label, satisfied, document_id | Required-document checklist |

## I. Configuration (the rules backbone)

| Table | Key columns | Notes |
|-------|-------------|-------|
| `config_sets` | id, name (rates_ct\|adjustments_ct\|validations_ct\|coa_map\|workflow_ct), version, effective_from, org_id (nullable=global), status (draft\|active\|retired), payload_json, legal_ref, created_by | Versioned, date-effective business rules |

## J. Audit & knowledge (shared)

| Table | Key columns | Notes | Status |
|-------|-------------|-------|--------|
| `audit_events` | id, actor_id, action, entity_type, entity_id, before_json, after_json, request_id, occurred_at | Append-only audit trail | NEW |
| `notifications` | id, user_id, company_id, type (deadline\|task\|finding), payload_json, read, created_at | Deadline/task alerts | NEW |
| `knowledge_documents` / `knowledge_chunks` | …, category='corporate_tax' | RAG corpus, regime-filtered | ✅ exists (add CT category) |

---

## Referential integrity & indexing

- All FKs enforced; cascade deletes only on owned children (e.g. `ct_computations`,
  `tax_adjustments` → `ct_returns`), `RESTRICT` on shared registers (companies, losses).
- Composite indexes: `(company_id, tax_period_id)`, `(ct_return_id, severity)`,
  `(regime, status)`, `(trial_balance_id, account_code)`.
- `general_ledger_entries` is the high-volume table — index `(company_id, tax_period_id,
  date)`, consider Postgres partitioning by tax period, and always paginate.
- Immutable tables (`ct_computations`, `filing_history`, `audit_events`) are insert-only.

## Migration path

Additive, matching the existing approach: `ensure_columns()` for column adds now, with
**Alembic** introduced when the CT tables land (the codebase already flags Alembic as the
Phase-4 successor to `create_all`). Existing VAT data is untouched — CT is new tables
plus the already-added `regime` discriminator.
