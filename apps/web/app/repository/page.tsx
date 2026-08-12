"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ReviewSummary } from "@/lib/types";
import { Card, RiskBadge, StatusBadge } from "@/components/ui";

export default function RepositoryPage() {
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [risk, setRisk] = useState("");
  const [status, setStatus] = useState("");
  const [compliance, setCompliance] = useState("");

  useEffect(() => {
    // Drill-down: pre-filter from ?risk= / ?status= / ?compliance= (dashboard tile click).
    const p = new URLSearchParams(window.location.search);
    const r = p.get("risk");
    const s = p.get("status");
    const c = p.get("compliance");
    if (r) setRisk(r);
    if (s) setStatus(s);
    if (c) setCompliance(c);
    api.listReviews().then(setReviews).catch((e) => setError(String(e.message ?? e)));
  }, []);

  const filtered = useMemo(
    () =>
      reviews.filter(
        (r) =>
          (!risk || r.risk_level === risk) &&
          (!status || r.status === status) &&
          (!compliance || r.compliance_status === compliance) &&
          (!q || `${r.filename} ${r.summary}`.toLowerCase().includes(q.toLowerCase())),
      ),
    [reviews, risk, status, compliance, q],
  );

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">Document Repository</h1>
        <p className="text-sm text-muted">Every reviewed document, searchable and filterable.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search filename or finding…"
          className="min-w-[220px] flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <select
          value={risk}
          onChange={(e) => setRisk(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
        >
          <option value="">All risk</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select
          value={compliance}
          onChange={(e) => setCompliance(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
        >
          <option value="">All results</option>
          <option value="pass">Pass</option>
          <option value="warning">Warning</option>
          <option value="fail">Fail</option>
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
        >
          <option value="">All status</option>
          {["draft", "pending", "approved", "rejected", "archived"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>
          Showing <b className="text-fg">{filtered.length}</b>
          {filtered.length !== reviews.length ? ` of ${reviews.length}` : ""} document
          {reviews.length === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          {(q || risk || status || compliance) && (
            <button
              onClick={() => { setQ(""); setRisk(""); setStatus(""); setCompliance(""); }}
              className="rounded-lg border border-border px-2.5 py-1 font-medium hover:bg-elevated"
            >
              Clear filters
            </button>
          )}
          {reviews.length > 0 &&
            (["csv", "xlsx"] as const).map((f) => (
              <a
                key={f}
                href={api.reviewsExportUrl(f, { risk, status, compliance, q })}
                className="rounded-lg border border-border px-2.5 py-1 font-medium hover:bg-elevated"
              >
                Export {f === "csv" ? "CSV" : "Excel"}
              </a>
            ))}
        </div>
      </div>

      {error && (
        <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>
      )}

      <Card className="overflow-hidden">
        {filtered.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-muted">No documents match.</div>
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((r) => (
              <li key={r.review_id}>
                <Link
                  href={`/review?id=${r.review_id}`}
                  className="flex items-center justify-between px-5 py-3 hover:bg-elevated"
                >
                  <div className="min-w-0">
                    <div className="truncate font-medium">{r.filename}</div>
                    <div className="truncate text-xs text-muted">{r.summary}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="rounded-full border border-border px-2 py-0.5 text-xs uppercase text-muted">
                      {r.status}
                    </span>
                    <RiskBadge risk={r.risk_level} />
                    <StatusBadge status={r.compliance_status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
