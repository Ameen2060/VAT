// Types mirroring the FastAPI backend responses.

export type ComplianceStatus = "pass" | "warning" | "fail";
export type RiskLevel = "low" | "medium" | "high";
export type Severity = "info" | "low" | "medium" | "high";
export type ReviewStatus = "draft" | "pending" | "approved" | "rejected" | "archived";

export interface ReviewSummary {
  review_id: string;
  document_id: string;
  filename: string;
  compliance_status: ComplianceStatus;
  risk_level: RiskLevel;
  status: ReviewStatus;
  read: boolean;
  summary: string;
}

export interface Finding {
  rule_id: string;
  severity: Severity;
  title: string;
  detail: string;
  legal_ref?: string | null;
  affects?: string | null;
  recommendation?: string | null;
}

export interface VerificationItem {
  field: string;
  label: string;
  confidence: number;
  status: string; // not_detected | low_confidence
  likely_present: boolean;
  reason: string;
  recommendation: string;
}

export interface ValidationCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface ReviewResult {
  compliance_status: ComplianceStatus;
  risk_level: RiskLevel;
  invoice_type: string;
  transaction_type: string;
  findings: Finding[];
  verification_items: VerificationItem[];
  validations: ValidationCheck[];
  requires_verification: boolean;
  recomputed_vat?: string | null;
  summary: string;
}

export interface Advisory {
  narrative: string;
  recommendations: string[];
  citations: string[];
  confidence: string;
  provider: string;
  grounded: boolean;
  llm_used?: boolean;
  error?: string | null;
}

// ── VAT201 return ────────────────────────────────────────────────────────────
export interface Vat201Box {
  box: string;
  label: string;
  amount: string;
  vat: string;
  count: number;
}

export interface Vat201Totals {
  total_sales_taxable: string;
  output_vat: string;
  reverse_charge_vat: string;
  total_expenses_taxable: string;
  recoverable_input_vat: string;
  net_vat_due: string;
  is_refund: boolean;
}

export interface Vat201ValidationIssue {
  severity: string;
  code: string;
  message: string;
  row_index?: number | null;
  invoice_number?: string | null;
}

export interface Vat201Return {
  company_name?: string | null;
  company_trn?: string | null;
  currency: string;
  period_type: string;
  period_label: string;
  period_start?: string | null;
  period_end?: string | null;
  due_date?: string | null;
  boxes: Vat201Box[];
  totals: Vat201Totals;
  validations: Vat201ValidationIssue[];
  transaction_count: number;
}

export interface Vat201ReturnSummary {
  id: string;
  company_name?: string | null;
  company_trn?: string | null;
  period_type: string;
  period_label: string;
  net_vat_due: string;
  is_refund: boolean;
  status: string;
  created_at?: string | null;
}

export interface Vat311Application {
  trn?: string | null;
  legal_name?: string | null;
  period_label?: string | null;
  total_excess_refundable: string;
  amount_requested: string;
  remaining_excess: string;
  late_registration_penalty: string;
  net_refund_expected: string;
  authorized_signatory?: string | null;
  declaration_date?: string | null;
  generated_at?: string | null;
}

export interface Vat201Txn {
  row_index: number;
  date?: string | null;
  doc_type?: string | null;
  direction?: string | null;
  party?: string | null;
  trn?: string | null;
  invoice_number?: string | null;
  emirate?: string | null;
  treatment?: string | null;
  taxable_amount: string;
  vat_amount: string;
  boxes: string[];
}

export interface AiStatus {
  configured: boolean;
  provider: string;
  active_provider: string;
  model: string;
  using_llm: boolean;
  ready: boolean;
  message: string;
}

export interface PartyDetails {
  name?: string | null;
  address?: string | null;
  trn?: string | null;
  phone?: string | null;
  email?: string | null;
}

export interface PaymentInfo {
  bank_name?: string | null;
  account_name?: string | null;
  account_number?: string | null;
  iban?: string | null;
  swift?: string | null;
  terms?: string | null;
}

export interface ExtractedLineItem {
  description?: string | null;
  quantity?: string | null;
  unit_price?: string | null;
  net_amount?: string | null;
  vat_rate?: string | null;
  vat_amount?: string | null;
  line_total?: string | null;
  treatment?: string | null;
}

export interface ExtractedInvoice {
  invoice_type?: string | null;
  invoice_number?: string | null;
  invoice_date?: string | null;
  supply_date?: string | null;
  due_date?: string | null;
  supplier?: PartyDetails;
  recipient?: PartyDetails;
  transaction_type?: string | null;
  treatment?: string | null;
  currency?: string | null;
  total_net?: string | null;
  total_vat?: string | null;
  total_gross?: string | null;
  discount_amount?: string | null;
  line_items?: ExtractedLineItem[];
  payment?: PaymentInfo | null;
  field_confidence?: Record<string, number>;
  field_evidence?: Record<
    string,
    { snippet: string; line_no: number; start: number; end: number; page?: number; bbox?: number[] }
  >;
  notes?: string | null;
  [key: string]: unknown;
}

export interface ReviewDetail {
  id: string;
  document_id: string;
  status: ReviewStatus;
  reviewer_notes?: string | null;
  compliance_status: ComplianceStatus;
  risk_level: RiskLevel;
  doc_type?: string;
  invoice: ExtractedInvoice;
  result: ReviewResult;
  advisory: Advisory;
  raw_text?: string | null;
  ocr_used?: boolean;
  ocr_engine?: string | null;
  extraction_warnings?: string[];
  missing_fields?: string[];
  file_url?: string;
  has_report?: boolean;
  report_url?: string;
  report_generated_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DashboardSummary {
  total_reviews: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  failed: number;
  warning: number;
  passed: number;
  pending_approval: number;
  approved: number;
}

export interface FtaSourceRef {
  tier: string;
  title: string;
  source_ref: string | null;
  effective_from: string | null;
}

export interface ChatResponse {
  reply: string;
  provider: string;
  citations: string[];
  grounded: boolean;
  vat_issue?: string | null;
  applicable_treatment?: string | null;
  effective_date?: string | null;
  validation_status?: string; // grounded | provisional | requires_sme
  provisional?: boolean;
  fta_sources?: FtaSourceRef[];
  audit_id?: string | null;
}

export interface KnowledgeDoc {
  id: string;
  title: string;
  source_ref: string | null;
  category: string;
  chunk_count: number;
}

export interface SearchHit {
  text: string;
  source_ref: string | null;
  title: string;
  score: number;
}

// ── Archive ──────────────────────────────────────────────────────────────────
export interface ArchiveRelated {
  kind: string | null;          // "review" | "vat_return" | null
  id: string | null;
  label: string | null;
  analysis_href: string | null; // frontend route to the analysis/details
  report_url: string | null;    // API path to download the related report/analysis
}

export interface ArchiveEntry {
  id: string;
  filename: string;
  mime: string | null;
  size_bytes: number;
  source: string;
  source_label: string;
  uploaded_by: string | null;
  created_at: string | null;
  file_url: string;
  related: ArchiveRelated;
  deleted_at: string | null;
  deleted_by: string | null;
  purge_in_days: number | null;
}

// ── FTA VAT Regulatory Updates ───────────────────────────────────────────────
export interface FtaValidationCheck {
  category: string;
  passed: boolean;
  detail: string;
}
export interface FtaValidation {
  passed: number;
  total: number;
  ok: boolean;
  checks: FtaValidationCheck[];
}
export interface FtaUpdate {
  id: string;
  title: string;
  update_type: string;
  classification: string; // informational | guidance | legally_effective
  status: string; // new | under_review | approved | implemented | rejected
  critical: boolean;
  publication_date: string | null;
  effective_date: string | null;
  previous_rule: string | null;
  new_rule: string | null;
  affected_module: string | null;
  affected_treatment: string | null;
  source_ref: string | null;
  notes: string | null;
  approved_by: string | null;
  implemented_at: string | null;
  validation: FtaValidation | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}
export interface FtaSource {
  id: string;
  name: string;
  url: string;
  authority: string;
  category: string;
  is_active: boolean;
  last_status: string; // unchecked | unchanged | changed | error
  last_checked_at: string | null;
  note: string | null;
}
export interface FtaRule {
  id: string;
  rule_key: string;
  title: string;
  category: string;
  value: string | null;
  effective_from: string;
  effective_to: string | null;
  source_ref: string;
  status: string;
}
export interface FtaDashboard {
  new: number;
  under_review: number;
  approved: number;
  implemented: number;
  rejected: number;
  critical: number;
  total: number;
  affected_modules: string[];
  upcoming_effective: {
    id: string;
    title: string;
    effective_date: string | null;
    status: string;
    affected_module: string | null;
    critical: boolean;
  }[];
  critical_pending: {
    id: string;
    title: string;
    status: string;
    effective_date: string | null;
    affected_module: string | null;
  }[];
  sources: Record<string, number>;
}
export type FtaUpdateInput = Partial<Omit<FtaUpdate, "id" | "status" | "validation" | "approved_by" | "implemented_at" | "created_by" | "created_at" | "updated_at">> & { title: string };
