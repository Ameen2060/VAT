"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ReviewDetail, ReviewStatus } from "@/lib/types";
import { Card, RiskBadge, SeverityDot, StatusBadge } from "@/components/ui";

const WORKFLOW: ReviewStatus[] = ["draft", "pending", "approved", "rejected", "archived"];

function Dropzone({ onFile, busy }: { onFile: (f: File) => void; busy: boolean }) {
  const [drag, setDrag] = useState(false);
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDrag(false);
      if (e.dataTransfer.files?.[0]) onFile(e.dataTransfer.files[0]);
    },
    [onFile],
  );

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
        drag ? "border-brand bg-brand/5" : "border-border bg-surface hover:bg-elevated"
      }`}
    >
      <input
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.webp,.xlsx,.csv,.docx,.zip"
        disabled={busy}
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
      <div className="text-4xl">📄</div>
      <div className="mt-2 font-medium">{busy ? "Analysing…" : "Drop an invoice or click to upload"}</div>
      <div className="mt-1 text-xs text-muted">PDF, image, Excel, CSV, Word or ZIP (batch)</div>
    </label>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="font-medium">{value ?? "—"}</div>
    </div>
  );
}

function Results({ detail, onStatus }: { detail: ReviewDetail; onStatus: (s: ReviewStatus) => void }) {
  const inv = detail.invoice ?? {};
  const sup = inv.supplier ?? {};
  const rec = inv.recipient ?? {};
  return (
    <div className="space-y-5 animate-in">
      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm text-muted">Invoice {inv.invoice_number ?? "—"}</div>
            <h2 className="text-lg font-semibold">{sup.name ?? "Unknown supplier"}</h2>
          </div>
          <div className="flex items-center gap-2">
            <RiskBadge risk={detail.risk_level} />
            <StatusBadge status={detail.compliance_status} />
          </div>
        </div>
        <p className="mt-3 text-sm text-muted">{detail.result?.summary}</p>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Field label="Date" value={inv.invoice_date} />
          <Field label="Supplier TRN" value={sup.trn} />
          <Field label="Recipient TRN" value={rec.trn} />
          <Field label="Recomputed VAT" value={detail.result?.recomputed_vat} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <a
            href={api.reviewReportUrl(detail.id, true)}
            className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-brand-fg hover:opacity-90"
          >
            Download PDF report
          </a>
          <a
            href={api.reviewReportUrl(detail.id, false)}
            target="_blank"
            className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-elevated"
          >
            View report
          </a>
        </div>
      </Card>

      {/* Approval workflow */}
      <Card className="flex flex-wrap items-center gap-2 p-4">
        <span className="text-sm text-muted">Status:</span>
        {WORKFLOW.map((s) => (
          <button
            key={s}
            onClick={() => onStatus(s)}
            className={`rounded-full px-3 py-1 text-xs font-semibold uppercase transition-colors ${
              detail.status === s ? "bg-brand text-brand-fg" : "border border-border text-muted hover:bg-elevated"
            }`}
          >
            {s}
          </button>
        ))}
      </Card>

      {/* Findings */}
      <Card className="overflow-hidden">
        <div className="border-b border-border px-5 py-4 font-semibold">
          Findings ({detail.result?.findings?.length ?? 0})
        </div>
        <div className="divide-y divide-border">
          {(detail.result?.findings ?? []).map((f, i) => (
            <div key={i} className="px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{f.title}</div>
                <SeverityDot severity={f.severity} />
              </div>
              <p className="mt-1 text-sm text-muted">{f.detail}</p>
              {f.legal_ref && <p className="mt-1 text-xs text-brand">{f.legal_ref}</p>}
              {f.recommendation && (
                <p className="mt-2 rounded-lg bg-elevated px-3 py-2 text-sm">
                  <span className="font-medium">Fix: </span>
                  {f.recommendation}
                </p>
              )}
            </div>
          ))}
          {(detail.result?.findings?.length ?? 0) === 0 && (
            <div className="px-5 py-8 text-center text-sm text-muted">No findings — fully compliant.</div>
          )}
        </div>
      </Card>

      {/* AI advisory */}
      <Card className="p-5">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold">AI Consultant Advisory</h3>
          <span className="text-xs text-muted">
            provider: {detail.advisory?.provider ?? "n/a"} · confidence: {detail.advisory?.confidence ?? "n/a"}
          </span>
        </div>
        <p className="whitespace-pre-line text-sm">{detail.advisory?.narrative}</p>
        {(detail.advisory?.recommendations?.length ?? 0) > 0 && (
          <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-muted">
            {detail.advisory.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export default function ReviewPage() {
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((id: string) => {
    api.getReview(id).then(setDetail).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) load(id);
  }, [load]);

  const onFile = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const summaries = await api.upload(file);
      if (summaries[0]) load(summaries[0].review_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onStatus = async (s: ReviewStatus) => {
    if (!detail) return;
    await api.setStatus(detail.id, s).catch(() => {});
    load(detail.id);
  };

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">Invoice Review</h1>
        <p className="text-sm text-muted">
          Upload an invoice for an automated UAE VAT compliance check.
        </p>
      </div>

      <Dropzone onFile={onFile} busy={busy} />

      {error && (
        <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>
      )}

      {detail && <Results detail={detail} onStatus={onStatus} />}
    </div>
  );
}
