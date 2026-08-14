"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ExtractedInvoice, PartyDetails, ReviewDetail } from "@/lib/types";
import { Card, RiskBadge, StatusBadge } from "@/components/ui";

// ── confidence helpers ───────────────────────────────────────────────────────
function confColor(score?: number) {
  if (score === undefined) return "bg-muted/40";
  if (score >= 0.8) return "bg-success";
  if (score >= 0.6) return "bg-warning";
  return "bg-danger";
}
function ConfDot({ score }: { score?: number }) {
  if (score === undefined) return null;
  return (
    <span className="ml-2 inline-flex items-center gap-1 text-[10px] text-muted" title={`confidence ${score}`}>
      <span className={`h-2 w-2 rounded-full ${confColor(score)}`} />
      {Math.round(score * 100)}%
    </span>
  );
}

function Dropzone({ onFile, busy }: { onFile: (f: File) => void; busy: boolean }) {
  const [drag, setDrag] = useState(false);
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (e.dataTransfer.files?.[0]) onFile(e.dataTransfer.files[0]);
      }}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
        drag ? "border-brand bg-brand/5" : "border-border bg-surface hover:bg-elevated"
      }`}
    >
      <input
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.webp,.tiff,.bmp,.xlsx,.csv,.docx,.zip"
        disabled={busy}
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
      <div className="text-3xl">🧾</div>
      <div className="mt-2 font-medium">{busy ? "Reading & extracting…" : "Upload an invoice or receipt"}</div>
      <div className="mt-1 text-xs text-muted">
        Scanned PDFs & images are OCR-processed automatically · PDF, image, Excel, CSV, Word, ZIP
      </div>
    </label>
  );
}

type Evidence = {
  snippet: string;
  line_no: number;
  start: number;
  end: number;
  page?: number;
  bbox?: number[];
};

// The document being analysed — set during render so SourceEvidence can build page-image
// URLs without threading the id through every Field.
let evidenceDocId: string | undefined;

// Level-4 source evidence: shows the exact document line a value was extracted from (text
// highlighted), and — when OCR/layout coordinates are available — the region on the page
// image, boxed.
function SourceEvidence({ ev }: { ev: Evidence }) {
  const documentId = evidenceDocId;
  const before = ev.snippet.slice(0, ev.start);
  const hit = ev.snippet.slice(ev.start, ev.end);
  const after = ev.snippet.slice(ev.end);
  const hasBox = documentId && ev.page != null && ev.bbox && ev.bbox.length === 4;
  const [x0, y0, x1, y1] = ev.bbox ?? [0, 0, 0, 0];
  const pad = 0.01; // small margin around the box
  return (
    <details className="ml-auto text-[10px]">
      <summary className="cursor-pointer select-none text-brand" title="Trace this value to the source document">
        ⌖ source
      </summary>
      <div className="mt-1 rounded-md border border-border bg-elevated px-2 py-1.5 font-mono text-[11px] leading-snug text-muted">
        <div className="mb-0.5 text-[9px] uppercase tracking-wide">
          line {ev.line_no + 1}
          {hasBox && <span> · page {(ev.page as number) + 1}</span>}
        </div>
        <span>{before}</span>
        <mark className="rounded bg-brand/25 px-0.5 text-fg">{hit || ev.snippet}</mark>
        <span>{after}</span>
        {hasBox && (
          <div className="relative mt-2 overflow-hidden rounded border border-border">
            <img
              src={api.pageUrl(documentId, ev.page as number)}
              alt="Source page"
              className="block w-full"
            />
            <div
              className="pointer-events-none absolute border-2 border-brand bg-brand/20"
              style={{
                left: `${Math.max(0, x0 - pad) * 100}%`,
                top: `${Math.max(0, y0 - pad) * 100}%`,
                width: `${Math.min(1, x1 - x0 + pad * 2) * 100}%`,
                height: `${Math.min(1, y1 - y0 + pad * 2) * 100}%`,
              }}
            />
          </div>
        )}
      </div>
    </details>
  );
}

// Editable text field with confidence indicator and (optional) source evidence.
function Field({
  label,
  value,
  onChange,
  score,
  evidence,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  score?: number;
  evidence?: Evidence;
}) {
  return (
    <label className="block">
      <span className="flex items-center text-xs uppercase tracking-wide text-muted">
        {label}
        <ConfDot score={score} />
        {evidence && <SourceEvidence ev={evidence} />}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand"
      />
    </label>
  );
}

const DOC_TYPE_LABELS: Record<string, string> = {
  tax_invoice: "Tax Invoice",
  simplified_tax_invoice: "Simplified Tax Invoice",
  credit_note: "Credit Note",
  debit_note: "Debit Note",
  receipt: "Receipt",
  invoice: "Invoice",
  unknown: "Unknown — Review required",
};

function prettyType(t?: string | null): string {
  if (!t) return "Unknown — Review required";
  return DOC_TYPE_LABELS[t] ?? t.replace(/_/g, " ");
}

function ReviewFlag({ text }: { text: string }) {
  return <div className="mt-1 text-[11px] font-medium text-warning">{text}</div>;
}

// A read-only labelled line for assessed (non-editable) party attributes.
function MetaLine({ label, value, tone }: { label: string; value?: string | null; tone?: "warn" | "ok" }) {
  return (
    <div className="text-sm">
      <span className="text-xs text-muted">{label}: </span>
      <span
        className={
          tone === "warn" ? "font-medium text-warning" : tone === "ok" ? "font-medium text-success" : "font-medium"
        }
      >
        {value || "Not detected — Review required"}
      </span>
    </div>
  );
}

// One party (customer or vendor). Always rendered — both sides are shown even when one
// is missing (spec §1), and an overseas party without a UAE TRN is "Not applicable".
function PartyCard({
  title,
  party,
  prefix,
  conf,
  ev,
  setField,
}: {
  title: string;
  party: PartyDetails;
  prefix: "supplier" | "recipient";
  conf: (k: string) => number | undefined;
  ev: (k: string) => Evidence | undefined;
  setField: (path: string, val: string) => void;
}) {
  const location =
    party.is_uae === true ? "UAE" : party.is_uae === false ? "Outside UAE" : "Unknown — Review required";
  const notDetected = !party.name && !party.trn;
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg">{title}</div>
      {notDetected && <ReviewFlag text="Not detected — Review required" />}
      <div className="space-y-2">
        <Field label="Name" value={party.name ?? ""} onChange={(v) => setField(`${prefix}.name`, v)} score={conf(`${prefix}.name`)} evidence={ev(`${prefix}.name`)} />
        <Field label="TRN" value={party.trn ?? ""} onChange={(v) => setField(`${prefix}.trn`, v)} score={conf(`${prefix}.trn`)} evidence={ev(`${prefix}.trn`)} />
        <MetaLine label="Country" value={party.country} />
        <MetaLine label="Location" value={location} tone={party.is_uae === false ? undefined : party.is_uae ? "ok" : "warn"} />
        <MetaLine
          label="VAT status"
          value={party.vat_registration_status}
          tone={
            (party.vat_registration_status || "").toLowerCase().includes("missing") ? "warn" : undefined
          }
        />
        <Field label="Address" value={party.address ?? ""} onChange={(v) => setField(`${prefix}.address`, v)} score={conf(`${prefix}.address`)} evidence={ev(`${prefix}.address`)} />
      </div>
    </div>
  );
}

export default function AnalyzePage() {
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [form, setForm] = useState<ExtractedInvoice | null>(null);
  const [tab, setTab] = useState<"fields" | "text">("fields");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [genReport, setGenReport] = useState(false);

  const load = useCallback((id: string) => {
    api
      .getReview(id)
      .then((d) => {
        setDetail(d);
        setForm(structuredClone(d.invoice));
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) load(id);
  }, [load]);

  const onFile = async (file: File) => {
    setBusy(true);
    setError(null);
    setSaved(false);
    setDetail(null);
    try {
      const summaries = await api.upload(file);
      if (summaries[0]) load(summaries[0].review_id);
      else setError("No invoice could be extracted from this file.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const conf = (key: string) => detail?.invoice?.field_confidence?.[key];
  const ev = (key: string) => detail?.invoice?.field_evidence?.[key];

  const setField = (path: string, val: string) => {
    setForm((prev) => {
      if (!prev) return prev;
      const next: ExtractedInvoice = structuredClone(prev);
      if (path.includes(".")) {
        const [a, b] = path.split(".");
        const obj = { ...(next[a] as Record<string, unknown> | undefined) };
        obj[b] = val;
        (next as Record<string, unknown>)[a] = obj;
      } else {
        (next as Record<string, unknown>)[path] = val;
      }
      return next;
    });
  };

  const save = async () => {
    if (!detail || !form) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateInvoice(detail.id, form);
      setSaved(true);
      load(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const reanalyze = async () => {
    if (!detail) return;
    setReanalyzing(true);
    setError(null);
    try {
      await api.reanalyze(detail.id);
      load(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReanalyzing(false);
    }
  };

  const generateReport = async () => {
    if (!detail) return;
    setGenReport(true);
    setError(null);
    try {
      await api.generateReport(detail.id);
      load(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenReport(false);
    }
  };

  evidenceDocId = detail?.document_id;
  const inv = form ?? {};
  const sup = inv.supplier ?? {};
  const rec = inv.recipient ?? {};
  const pay = inv.payment ?? {};
  const adv = detail?.advisory;

  // Report is "stale" if the review changed meaningfully after the PDF was generated
  // (5s tolerance absorbs the generation commit itself).
  const reportStale =
    !!detail?.has_report &&
    !!detail?.report_generated_at &&
    !!detail?.updated_at &&
    new Date(detail.updated_at).getTime() - new Date(detail.report_generated_at).getTime() > 5000;

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">Document Analysis</h1>
        <p className="text-sm text-muted">
          Upload any invoice or receipt — the system reads it (OCR for scans), extracts structured
          fields with confidence scores, and lets you review &amp; correct before saving.
        </p>
      </div>

      <Dropzone onFile={onFile} busy={busy} />

      {error && (
        <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>
      )}

      {detail && form && (
        <>
          {/* Meta banner */}
          <Card className="flex flex-wrap items-center gap-3 p-4">
            <span className="rounded-full bg-brand/15 px-3 py-1 text-xs font-semibold uppercase text-brand">
              {detail.doc_type?.replace(/_/g, " ") ?? "document"}
            </span>
            {detail.ocr_used && (
              <span className="rounded-full border border-border px-3 py-1 text-xs text-muted">
                OCR: {detail.ocr_engine}
              </span>
            )}
            <RiskBadge risk={detail.risk_level} />
            <StatusBadge status={detail.compliance_status} />
            {detail.missing_fields && detail.missing_fields.length > 0 && (
              <span className="text-xs text-warning">
                Missing/low-confidence: {detail.missing_fields.join(", ")}
              </span>
            )}
            {detail.extraction_warnings && detail.extraction_warnings.length > 0 && (
              <span className="text-xs text-danger">⚠ {detail.extraction_warnings.join("; ")}</span>
            )}
          </Card>

          {/* Requires Verification — extraction gaps, do NOT affect Pass/Fail */}
          {detail.result?.verification_items && detail.result.verification_items.length > 0 && (
            <Card className="border-warning/40 p-5">
              <div className="flex items-center gap-2">
                <h2 className="font-semibold">Requires Verification</h2>
                <span className="rounded-full bg-warning/15 px-2 py-0.5 text-xs font-semibold text-warning">
                  {detail.result.verification_items.length}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted">
                These fields weren&apos;t confidently extracted. They do <b>not</b> affect the
                Pass/Fail verdict — check the original and confirm/edit them in the fields panel.
              </p>
              <ul className="mt-3 divide-y divide-border">
                {detail.result.verification_items.map((v, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{v.label}</div>
                      <div className="text-xs text-muted">{v.reason}</div>
                    </div>
                    <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-xs text-muted">
                      {v.status === "low_confidence"
                        ? `Low confidence ${Math.round(v.confidence * 100)}%`
                        : v.likely_present
                          ? "Not detected · likely present"
                          : "Not detected"}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {/* Data Validation cross-checks (transparency before the verdict) */}
          {detail.result?.validations && detail.result.validations.length > 0 && (
            <Card className="p-5">
              <h2 className="font-semibold">Data Validation</h2>
              <p className="mt-1 text-xs text-muted">
                Cross-checks on the extracted values, performed before the compliance verdict.
              </p>
              <ul className="mt-3 space-y-1.5 text-sm">
                {detail.result.validations.map((c, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className={c.passed ? "text-success" : "text-danger"}>
                      {c.passed ? "✓" : "✕"}
                    </span>
                    <span className="font-medium">{c.name}</span>
                    <span className="truncate text-xs text-muted">— {c.detail}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="grid gap-5 lg:grid-cols-2">
            {/* Original document */}
            <Card className="overflow-hidden">
              <div className="border-b border-border px-4 py-3 text-sm font-semibold">Original document</div>
              {detail.file_url && (
                <iframe
                  src={api.fileUrl(detail.document_id)}
                  className="h-[620px] w-full bg-white"
                  title="Original document"
                />
              )}
            </Card>

            {/* Extraction panel */}
            <Card className="flex flex-col overflow-hidden">
              <div className="flex border-b border-border">
                {(["fields", "text"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`px-4 py-3 text-sm font-medium ${
                      tab === t ? "border-b-2 border-brand text-fg" : "text-muted"
                    }`}
                  >
                    {t === "fields" ? "Structured fields" : "Extracted text"}
                  </button>
                ))}
              </div>

              {tab === "text" ? (
                <pre className="h-[560px] overflow-auto whitespace-pre-wrap p-4 text-xs text-muted">
                  {detail.raw_text || "(no text extracted)"}
                </pre>
              ) : (
                <div className="h-[560px] space-y-4 overflow-auto p-4">
                  {/* Conclusion (PASS / FAIL / REVIEW) */}
                  {detail.result?.conclusion && (
                    <div
                      className={`rounded-lg border px-3 py-2 text-sm ${
                        detail.result.conclusion === "pass"
                          ? "border-success/40 bg-success/5 text-success"
                          : detail.result.conclusion === "fail"
                            ? "border-danger/40 bg-danger/5 text-danger"
                            : "border-warning/40 bg-warning/5 text-warning"
                      }`}
                    >
                      <span className="font-semibold uppercase">{detail.result.conclusion}</span>
                      {detail.result.conclusion_reason ? ` — ${detail.result.conclusion_reason}` : ""}
                    </div>
                  )}

                  {/* Document information — always visible */}
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted">Document information</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="text-sm">
                      <div className="text-xs text-muted">Document type</div>
                      <div className="font-medium">{prettyType(inv.invoice_type)}</div>
                    </div>
                    <div className="text-sm">
                      <div className="text-xs text-muted">Place of supply</div>
                      <div className="font-medium">{detail.result?.place_of_supply || "—"}</div>
                    </div>
                    <div>
                      <Field label="Invoice number" value={inv.invoice_number ?? ""} onChange={(v) => setField("invoice_number", v)} score={conf("invoice_number")} evidence={ev("invoice_number")} />
                      {!inv.invoice_number && <ReviewFlag text="Invoice Number: Not detected — Review required" />}
                    </div>
                    <div>
                      <Field label="Invoice date" value={inv.invoice_date ?? ""} onChange={(v) => setField("invoice_date", v)} score={conf("invoice_date")} evidence={ev("invoice_date")} />
                      {inv.invoice_date_original && inv.invoice_date_original !== inv.invoice_date && (
                        <div className="mt-1 text-[11px] text-muted">As printed: {inv.invoice_date_original}</div>
                      )}
                      {!inv.invoice_date && <ReviewFlag text="Invoice Date: Not detected — Review required" />}
                    </div>
                    <Field label="Due date" value={inv.due_date ?? ""} onChange={(v) => setField("due_date", v)} score={conf("due_date")} evidence={ev("due_date")} />
                    <Field label="Currency" value={inv.currency ?? ""} onChange={(v) => setField("currency", v)} score={conf("currency")} />
                  </div>

                  {/* Customer / Buyer and Vendor / Supplier — both always shown */}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <PartyCard
                      title="Customer / Buyer"
                      party={rec}
                      prefix="recipient"
                      conf={conf}
                      ev={ev}
                      setField={setField}
                    />
                    <PartyCard
                      title="Vendor / Supplier"
                      party={sup}
                      prefix="supplier"
                      conf={conf}
                      ev={ev}
                      setField={setField}
                    />
                  </div>

                  {/* VAT result — tax code + independent recalculation */}
                  {detail.result?.tax_code && (
                    <div className="rounded-lg border border-border p-3">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg">VAT result</div>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                        <div>
                          <span className="text-muted">Tax code: </span>
                          <b>{detail.result.tax_code}</b>
                          {detail.result.tax_code_name ? ` — ${detail.result.tax_code_name}` : ""}
                        </div>
                        <div>
                          <span className="text-muted">VAT treatment: </span>
                          {detail.result.detected_treatment
                            ? detail.result.detected_treatment.replace(/_/g, " ")
                            : detail.result.tax_code_name || "—"}
                        </div>
                        <div>
                          <span className="text-muted">Taxable amount: </span>
                          {detail.result.taxable_amount ?? "—"}
                        </div>
                        <div>
                          <span className="text-muted">VAT amount (invoice): </span>
                          {inv.total_vat ?? "—"}
                        </div>
                        <div>
                          <span className="text-muted">Expected VAT: </span>
                          {detail.result.expected_vat ?? "—"}
                        </div>
                        <div
                          className={
                            detail.result.vat_difference && Number(detail.result.vat_difference) !== 0
                              ? "font-medium text-danger"
                              : ""
                          }
                        >
                          <span className="text-muted">Difference: </span>
                          {detail.result.vat_difference ?? "—"}
                        </div>
                        <div className="col-span-2">
                          <span className="text-muted">Result: </span>
                          <b
                            className={
                              detail.result.conclusion === "pass"
                                ? "text-success"
                                : detail.result.conclusion === "fail"
                                  ? "text-danger"
                                  : "text-warning"
                            }
                          >
                            {(detail.result.conclusion ?? "review").toUpperCase()}
                          </b>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="text-xs font-semibold uppercase text-muted">Totals</div>
                  <div className="grid grid-cols-3 gap-3">
                    <Field label="Net" value={inv.total_net ?? ""} onChange={(v) => setField("total_net", v)} score={conf("total_net")} evidence={ev("total_net")} />
                    <Field label="VAT" value={inv.total_vat ?? ""} onChange={(v) => setField("total_vat", v)} score={conf("total_vat")} evidence={ev("total_vat")} />
                    <Field label="Gross" value={inv.total_gross ?? ""} onChange={(v) => setField("total_gross", v)} score={conf("total_gross")} evidence={ev("total_gross")} />
                  </div>

                  {inv.line_items && inv.line_items.length > 0 && (
                    <>
                      <div className="text-xs font-semibold uppercase text-muted">
                        Line items <ConfDot score={conf("line_items")} />
                      </div>
                      <div className="overflow-x-auto rounded-lg border border-border">
                        <table className="w-full text-xs">
                          <thead className="bg-elevated text-muted">
                            <tr>
                              <th className="px-2 py-1.5 text-left">Description</th>
                              <th className="px-2 py-1.5 text-right">Net</th>
                              <th className="px-2 py-1.5 text-right">VAT</th>
                              <th className="px-2 py-1.5 text-right">Total</th>
                            </tr>
                          </thead>
                          <tbody>
                            {inv.line_items.map((li, i) => (
                              <tr key={i} className="border-t border-border">
                                <td className="px-2 py-1.5">{li.description ?? "—"}</td>
                                <td className="px-2 py-1.5 text-right">{li.net_amount ?? "—"}</td>
                                <td className="px-2 py-1.5 text-right">{li.vat_amount ?? "—"}</td>
                                <td className="px-2 py-1.5 text-right">{li.line_total ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  <div className="text-xs font-semibold uppercase text-muted">Payment</div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Bank" value={pay.bank_name ?? ""} onChange={(v) => setField("payment.bank_name", v)} />
                    <Field label="Account #" value={pay.account_number ?? ""} onChange={(v) => setField("payment.account_number", v)} />
                    <Field label="IBAN" value={pay.iban ?? ""} onChange={(v) => setField("payment.iban", v)} score={conf("payment.iban")} />
                    <Field label="SWIFT" value={pay.swift ?? ""} onChange={(v) => setField("payment.swift", v)} />
                  </div>
                </div>
              )}

              <div className="flex items-center gap-3 border-t border-border p-3">
                <button
                  onClick={save}
                  disabled={saving}
                  className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save & re-check compliance"}
                </button>
                <a
                  href={api.reportUrl(detail.id, "pdf")}
                  className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated"
                >
                  Download report
                </a>
                {saved && <span className="text-sm text-success">Saved ✓</span>}
              </div>
            </Card>
          </div>

          {/* AI Analysis */}
          <Card className="p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h2 className="font-semibold">AI Analysis</h2>
                {adv?.llm_used ? (
                  <span className="rounded-full bg-brand/15 px-2.5 py-0.5 text-xs font-semibold uppercase text-brand">
                    {adv.provider}
                  </span>
                ) : (
                  <span className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted">
                    Deterministic (no LLM)
                  </span>
                )}
                {adv?.confidence && adv.confidence !== "n/a" && (
                  <span className="text-xs text-muted">confidence: {adv.confidence}</span>
                )}
              </div>
              <button
                onClick={reanalyze}
                disabled={reanalyzing}
                className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-elevated disabled:opacity-50"
              >
                {reanalyzing ? "Analysing…" : "Re-run AI analysis"}
              </button>
            </div>

            {adv?.error && (
              <div className="mb-3 rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">
                AI error: {adv.error}
              </div>
            )}

            <p className="whitespace-pre-line text-sm">{adv?.narrative}</p>

            {adv?.recommendations && adv.recommendations.length > 0 && (
              <>
                <div className="mt-4 text-xs font-semibold uppercase text-muted">Recommendations</div>
                <ul className="mt-1 list-inside list-disc space-y-1 text-sm text-muted">
                  {adv.recommendations.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </>
            )}

            {adv?.citations && adv.citations.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {adv.citations.map((c, i) => (
                  <span key={i} className="rounded-md border border-border px-2 py-0.5 text-xs text-brand">
                    {c}
                  </span>
                ))}
              </div>
            )}
            {!adv?.llm_used && (
              <p className="mt-3 text-xs text-muted">
                Add an API key in <code>apps/api/.env</code> and click “Re-run AI analysis” for a
                full consultant-style interpretation.
              </p>
            )}
          </Card>

          {/* Complete Review Report */}
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-semibold">Complete Review Report</h2>
                <p className="text-xs text-muted">
                  {detail.has_report
                    ? `PDF generated ${detail.report_generated_at ? new Date(detail.report_generated_at).toLocaleString() : ""}`
                    : "A single PDF combining the document data, compliance review, AI analysis, findings, recommendations and verdict."}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <a
                  href={api.reviewReportUrl(detail.id, true)}
                  className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-brand-fg hover:opacity-90"
                >
                  Download combined PDF
                </a>
                <a
                  href={api.reviewReportUrl(detail.id, false)}
                  target="_blank"
                  className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-elevated"
                >
                  View report
                </a>
                <button
                  onClick={generateReport}
                  disabled={genReport}
                  className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-elevated disabled:opacity-50"
                >
                  {genReport ? "Generating…" : detail.has_report ? "Regenerate PDF" : "Generate PDF"}
                </button>
              </div>
            </div>

            {reportStale && (
              <div className="mt-3 rounded-lg border border-warning/40 bg-warning/5 px-3 py-2 text-sm text-warning">
                The review has changed since this report was generated — click “Regenerate PDF” to
                refresh it.
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-3 text-sm">
              <a
                href={api.fileUrl(detail.document_id)}
                target="_blank"
                className="rounded-lg border border-border px-3 py-1.5 font-medium hover:bg-elevated"
              >
                Open original document
              </a>
              <Link
                href={`/review?id=${detail.id}`}
                className="rounded-lg border border-border px-3 py-1.5 font-medium hover:bg-elevated"
              >
                View compliance review
              </Link>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
