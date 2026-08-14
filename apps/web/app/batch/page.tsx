"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card } from "@/components/ui";

// File types the analyzer supports.
const SUPPORTED = [
  "pdf", "jpg", "jpeg", "png", "webp", "gif", "tiff", "bmp",
  "xlsx", "xls", "xlsm", "docx", "doc", "csv", "txt",
];
const MAX_MB = 25;
const CONCURRENCY = 3; // safe parallel uploads so the browser never freezes

type Row = {
  file: File;
  path: string;            // folder path (without filename)
  ext: string;
  status: "pending" | "processing" | "done" | "review" | "failed" | "duplicate";
  error?: string;
  reviewId?: string;
  compliance?: string;
  risk?: string;
};

function ext(name: string) {
  return name.split(".").pop()?.toLowerCase() ?? "";
}
function fmtSize(n: number) {
  return n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
}

export default function BatchPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (fileList: FileList | null) => {
    if (!fileList) return;
    const next: Row[] = [];
    for (const f of Array.from(fileList)) {
      const e = ext(f.name);
      if (!SUPPORTED.includes(e)) continue;                 // skip unsupported
      const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
      const path = rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "";
      next.push({ file: f, path, ext: e, status: "pending" });
    }
    // Flag likely duplicates within the selection (same name + size).
    const seen = new Map<string, number>();
    next.forEach((r) => {
      const k = `${r.file.name}:${r.file.size}`;
      seen.set(k, (seen.get(k) ?? 0) + 1);
    });
    next.forEach((r) => {
      if ((seen.get(`${r.file.name}:${r.file.size}`) ?? 0) > 1) r.status = "duplicate";
    });
    setRows(next);
    setDone(false);
  };

  const analyzeAll = async () => {
    setRunning(true);
    setDone(false);
    const queue = rows.map((_, i) => i).filter((i) => rows[i].status !== "duplicate");
    let cursor = 0;

    const worker = async () => {
      while (cursor < queue.length) {
        const idx = queue[cursor++];
        setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, status: "processing" } : r)));
        try {
          const r = rows[idx];
          const oversize = r.file.size > MAX_MB * 1048576;
          if (oversize) throw new Error(`File exceeds ${MAX_MB} MB`);
          const res = await api.upload(r.file, "invoice", r.path || undefined);
          const first = res[0];
          setRows((prev) =>
            prev.map((row, i) =>
              i === idx
                ? {
                    ...row,
                    status: first?.duplicate
                      ? "duplicate"
                      : first?.compliance_status === "fail"
                        ? "failed"
                        : first?.status === "pending" || first?.compliance_status === "warning"
                          ? "review"
                          : "done",
                    reviewId: first?.review_id,
                    compliance: first?.compliance_status,
                    risk: first?.risk_level,
                  }
                : row,
            ),
          );
        } catch (e) {
          setRows((prev) =>
            prev.map((row, i) =>
              i === idx ? { ...row, status: "failed", error: (e as Error).message } : row,
            ),
          );
        }
      }
    };

    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    setRunning(false);
    setDone(true);
  };

  const stats = useMemo(() => {
    const s = { total: rows.length, processed: 0, successful: 0, review: 0, failed: 0, duplicate: 0 };
    for (const r of rows) {
      if (["done", "review", "failed"].includes(r.status)) s.processed++;
      if (r.status === "done") s.successful++;
      if (r.status === "review") s.review++;
      if (r.status === "failed") s.failed++;
      if (r.status === "duplicate") s.duplicate++;
    }
    return s;
  }, [rows]);

  const pct = stats.total ? Math.round((stats.processed / (stats.total - stats.duplicate || 1)) * 100) : 0;

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">Folder Analysis</h1>
        <p className="text-sm text-muted">
          Upload an entire folder — every supported document is analysed individually (invoice
          number/date, customer &amp; vendor, UAE VAT treatment, PASS/FAIL/REVIEW) and archived.
        </p>
      </div>

      {/* Folder picker */}
      <Card className="p-5">
        <input
          ref={inputRef}
          type="file"
          multiple
          onChange={(e) => pick(e.target.files)}
          className="hidden"
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => inputRef.current?.click()}
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2.5 font-semibold text-brand-fg hover:opacity-90"
          >
            📁 Upload Folder for Analysis
          </button>
          {rows.length > 0 && (
            <button
              onClick={analyzeAll}
              disabled={running}
              className="rounded-lg border border-border px-4 py-2.5 font-medium hover:bg-elevated disabled:opacity-50"
            >
              {running ? "Analysing…" : `Analyze All Documents (${rows.length - stats.duplicate})`}
            </button>
          )}
          <span className="text-xs text-muted">
            Supported: PDF, JPG, PNG, XLSX, XLS, DOCX, CSV · subfolders included · ≤{MAX_MB} MB each
          </span>
        </div>
      </Card>

      {/* Progress + results */}
      {rows.length > 0 && (
        <Card className="p-5">
          <div className="mb-3 h-2 w-full overflow-hidden rounded-full bg-elevated">
            <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${pct}%` }} />
          </div>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
            <Stat label="Found" value={stats.total} />
            <Stat label="Processed" value={stats.processed} />
            <Stat label="Successful" value={stats.successful} tone="ok" href="/repository?compliance=pass" />
            <Stat label="Review" value={stats.review} tone="warn" href="/repository?status=pending" />
            <Stat label="Failed" value={stats.failed} tone="bad" href="/repository?compliance=fail" />
            <Stat label="Duplicates" value={stats.duplicate} tone="warn" />
          </div>
          {done && (
            <div className="mt-4 rounded-lg border border-success/40 bg-success/5 px-3 py-2 text-sm text-success">
              Batch complete — {stats.successful} passed, {stats.review} need review, {stats.failed} failed,
              {" "}{stats.duplicate} duplicate(s) skipped. Open any document below or in the Repository.
            </div>
          )}
        </Card>
      )}

      {/* File list */}
      {rows.length > 0 && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b border-border text-left text-xs uppercase text-muted">
                <tr>
                  <th className="px-4 py-2">File</th>
                  <th className="px-4 py-2">Folder</th>
                  <th className="px-4 py-2">Type</th>
                  <th className="px-4 py-2">Size</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((r, i) => (
                  <tr key={i} className="hover:bg-elevated">
                    <td className="max-w-[220px] truncate px-4 py-2 font-medium">{r.file.name}</td>
                    <td className="max-w-[200px] truncate px-4 py-2 text-muted">{r.path || "—"}</td>
                    <td className="px-4 py-2 uppercase text-muted">{r.ext}</td>
                    <td className="px-4 py-2 text-muted">{fmtSize(r.file.size)}</td>
                    <td className="px-4 py-2"><StatusPill status={r.status} error={r.error} /></td>
                    <td className="px-4 py-2 text-right">
                      {r.reviewId && (
                        <Link href={`/review?id=${r.reviewId}`} className="text-brand hover:underline">
                          View
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value, tone, href }: { label: string; value: number; tone?: "ok" | "warn" | "bad"; href?: string }) {
  const color =
    tone === "ok" ? "text-success" : tone === "warn" ? "text-warning" : tone === "bad" ? "text-danger" : "text-fg";
  const body = (
    <div className="rounded-lg border border-border p-3 text-center">
      <div className={`text-xl font-semibold ${color}`}>{value}</div>
      <div className="text-[11px] uppercase text-muted">{label}</div>
    </div>
  );
  return href && value > 0 ? <Link href={href}>{body}</Link> : body;
}

function StatusPill({ status, error }: { status: Row["status"]; error?: string }) {
  const map: Record<Row["status"], string> = {
    pending: "border-border text-muted",
    processing: "border-brand/40 text-brand",
    done: "border-success/40 text-success",
    review: "border-warning/40 text-warning",
    failed: "border-danger/40 text-danger",
    duplicate: "border-warning/40 text-warning",
  };
  const label: Record<Row["status"], string> = {
    pending: "Pending",
    processing: "Processing…",
    done: "Pass",
    review: "Review",
    failed: "Failed",
    duplicate: "Duplicate",
  };
  return (
    <span title={error} className={`rounded-full border px-2 py-0.5 text-xs ${map[status]}`}>
      {label[status]}
    </span>
  );
}
