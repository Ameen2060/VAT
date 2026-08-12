"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DashboardSummary, ReviewStatus, ReviewSummary, RiskLevel } from "@/lib/types";
import { Card, StatusBadge } from "@/components/ui";
import { ActionMenu } from "@/components/action-menu";
import { FtaSummary } from "@/components/fta-summary";

function Kpi({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <Card className="p-5">
      <div className="text-sm text-muted">{label}</div>
      <div className={`mt-1 text-3xl font-semibold ${tone}`}>{value}</div>
    </Card>
  );
}

function RiskBar({ d }: { d: DashboardSummary }) {
  const total = Math.max(d.high_risk + d.medium_risk + d.low_risk, 1);
  const seg = (n: number, cls: string) =>
    n > 0 ? <div className={cls} style={{ width: `${(n / total) * 100}%` }} /> : null;
  return (
    <div className="flex h-3 overflow-hidden rounded-full bg-elevated">
      {seg(d.high_risk, "bg-danger")}
      {seg(d.medium_risk, "bg-warning")}
      {seg(d.low_risk, "bg-success")}
    </div>
  );
}

const STATUS_STYLE: Record<ReviewStatus, string> = {
  draft: "border-border text-muted",
  pending: "border-warning/40 text-warning",
  approved: "border-success/40 text-success bg-success/10",
  rejected: "border-danger/40 text-danger bg-danger/10",
  archived: "border-border text-muted",
};

function WorkflowPill({ status }: { status: ReviewStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase ${STATUS_STYLE[status] ?? STATUS_STYLE.draft}`}
    >
      {status}
    </span>
  );
}

interface RowProps {
  r: ReviewSummary;
  busy: boolean;
  onStatus: (status: ReviewStatus) => void;
  onRead: (read: boolean) => void;
  onDelete: () => void;
}

function IssueRow({ r, busy, onStatus, onRead, onDelete }: RowProps) {
  return (
    <li className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-elevated">
      <Link href={`/analyze?id=${r.review_id}`} className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {!r.read && (
            <span className="h-2 w-2 shrink-0 rounded-full bg-brand" title="Unread" aria-label="unread" />
          )}
          <span className={`truncate font-medium ${r.read ? "text-muted" : ""}`}>{r.filename}</span>
        </div>
        <div className="truncate text-xs text-muted">{r.summary}</div>
      </Link>

      <div className="flex shrink-0 items-center gap-2">
        <WorkflowPill status={r.status} />
        <StatusBadge status={r.compliance_status} />
        <ActionMenu
          ariaLabel="Issue actions"
          busy={busy}
          items={[
            { label: "Mark as Approved", icon: "✓", onSelect: () => onStatus("approved") },
            { label: "Mark as Rejected", icon: "✕", onSelect: () => onStatus("rejected") },
            {
              label: r.read ? "Mark as Unread" : "Mark as Read",
              icon: "●",
              onSelect: () => onRead(!r.read),
            },
            { label: "Delete", icon: "🗑", danger: true, onSelect: onDelete },
          ]}
        />
      </div>
    </li>
  );
}

const SECTIONS: { level: RiskLevel; title: string; dot: string }[] = [
  { level: "high", title: "High Risk Issues", dot: "bg-danger" },
  { level: "medium", title: "Medium Risk Issues", dot: "bg-warning" },
  { level: "low", title: "Low Risk Issues", dot: "bg-success" },
];

export default function DashboardPage() {
  const [d, setD] = useState<DashboardSummary | null>(null);
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<ReviewSummary | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [summary, list] = await Promise.all([api.dashboard(), api.listReviews()]);
      setD(summary);
      setReviews(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const changeStatus = async (id: string, status: ReviewStatus) => {
    setBusyId(id);
    try {
      await api.setStatus(id, status);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const markRead = async (id: string, read: boolean) => {
    setBusyId(id);
    try {
      await api.markRead(id, read);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    const id = confirmDelete.review_id;
    setConfirmDelete(null);
    setBusyId(id);
    try {
      await api.deleteReview(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Compliance Overview</h1>
          <p className="text-sm text-muted">Your UAE VAT compliance at a glance.</p>
        </div>
        <Link
          href="/analyze"
          className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg hover:opacity-90"
        >
          + Review invoice
        </Link>
      </div>

      {error && (
        <Card className="border-warning/40 bg-warning/5 p-4 text-sm text-warning">
          <div className="flex items-center justify-between gap-3">
            <span>⚠️ {error}</span>
            <button
              onClick={() => refresh()}
              className="shrink-0 rounded-lg border border-warning/40 px-3 py-1 text-xs font-medium hover:bg-warning/10"
            >
              Retry
            </button>
          </div>
        </Card>
      )}

      {d && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Invoices reviewed" value={d.total_reviews} />
            <Kpi label="High-risk issues" value={d.high_risk} tone="text-danger" />
            <Kpi label="Medium-risk issues" value={d.medium_risk} tone="text-warning" />
            <Kpi label="Low-risk issues" value={d.low_risk} tone="text-success" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-semibold">Risk distribution</h2>
                <span className="text-xs text-muted">
                  {d.failed} fail · {d.warning} warning · {d.passed} pass
                </span>
              </div>
              <RiskBar d={d} />
              <div className="mt-3 flex gap-4 text-xs text-muted">
                <span className="flex items-center gap-1.5">
                  <i className="inline-block h-2 w-2 rounded-full bg-danger" /> High {d.high_risk}
                </span>
                <span className="flex items-center gap-1.5">
                  <i className="inline-block h-2 w-2 rounded-full bg-warning" /> Medium {d.medium_risk}
                </span>
                <span className="flex items-center gap-1.5">
                  <i className="inline-block h-2 w-2 rounded-full bg-success" /> Low {d.low_risk}
                </span>
              </div>
            </Card>
            <Card className="p-5">
              <h2 className="mb-3 font-semibold">Approval queue</h2>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted">Pending review</span>
                  <span className="font-medium">{d.pending_approval}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Approved</span>
                  <span className="font-medium">{d.approved}</span>
                </div>
              </div>
            </Card>
          </div>

          {/* FTA VAT regulatory updates summary */}
          <FtaSummary />

          {/* Risk-grouped issue lists with per-issue actions */}
          {SECTIONS.map((section) => {
            const items = reviews.filter((r) => r.risk_level === section.level);
            return (
              <Card key={section.level} className="overflow-hidden">
                <div className="flex items-center justify-between border-b border-border px-5 py-4">
                  <h2 className="flex items-center gap-2 font-semibold">
                    <span className={`inline-block h-2.5 w-2.5 rounded-full ${section.dot}`} />
                    {section.title}
                  </h2>
                  <span className="rounded-full bg-elevated px-2.5 py-0.5 text-xs text-muted">
                    {items.length}
                  </span>
                </div>
                {items.length === 0 ? (
                  <div className="px-5 py-8 text-center text-sm text-muted">
                    No {section.level}-risk issues.
                  </div>
                ) : (
                  <ul className="divide-y divide-border">
                    {items.map((r) => (
                      <IssueRow
                        key={r.review_id}
                        r={r}
                        busy={busyId === r.review_id}
                        onStatus={(status) => changeStatus(r.review_id, status)}
                        onRead={(read) => markRead(r.review_id, read)}
                        onDelete={() => setConfirmDelete(r)}
                      />
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </>
      )}

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-md p-5">
            <h3 className="text-lg font-semibold">Delete this issue?</h3>
            <p className="mt-2 text-sm text-muted">
              This permanently deletes the review for{" "}
              <span className="font-medium text-fg">{confirmDelete.filename}</span> and its stored
              document/report. This cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated"
              >
                Cancel
              </button>
              <button
                onClick={doDelete}
                className="rounded-lg bg-danger px-4 py-2 text-sm font-medium text-white hover:opacity-90"
              >
                Delete
              </button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
