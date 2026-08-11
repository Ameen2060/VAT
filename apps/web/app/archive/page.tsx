"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";
import type { ArchiveEntry } from "@/lib/types";
import { Card } from "@/components/ui";

const SOURCE_STYLE: Record<string, string> = {
  document_analysis: "bg-brand/15 text-brand",
  invoice_review: "bg-brand/15 text-brand",
  vat_return: "bg-success/15 text-success",
  assistant: "bg-warning/15 text-warning",
};

function humanSize(n: number) {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

function fileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "📄";
  if (["xlsx", "xls", "csv"].includes(ext)) return "📊";
  if (["png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff"].includes(ext)) return "🖼️";
  if (["doc", "docx"].includes(ext)) return "📝";
  return "📎";
}

type View = "active" | "deleted";

export default function ArchivePage() {
  const [items, setItems] = useState<ArchiveEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [view, setView] = useState<View>("active");
  const [busyId, setBusyId] = useState<string | null>(null);
  // Confirmation modal — permanent flag distinguishes soft-delete vs hard-delete.
  const [confirm, setConfirm] = useState<{ entry: ArchiveEntry; permanent: boolean } | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkConfirm, setBulkConfirm] = useState<{ action: "delete" | "permanent"; count: number } | null>(null);

  const load = (v: View) => {
    setLoading(true);
    setSelected(new Set());
    api
      .listArchive({ deleted: v === "deleted" })
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setIsAdmin(getUser()?.role === "admin");
    load("active");
  }, []);

  const switchView = (v: View) => {
    if (v === view) return;
    setView(v);
    setError(null);
    setItems([]);
    load(v);
  };

  const doDelete = async () => {
    if (!confirm) return;
    const { entry, permanent } = confirm;
    setConfirm(null);
    setBusyId(entry.id);
    setError(null);
    try {
      await api.deleteArchive(entry.id, permanent);
      setItems((prev) => prev.filter((x) => x.id !== entry.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const restore = async (entry: ArchiveEntry) => {
    setBusyId(entry.id);
    setError(null);
    try {
      await api.restoreArchive(entry.id);
      setItems((prev) => prev.filter((x) => x.id !== entry.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const sources = useMemo(() => {
    const map = new Map<string, string>();
    items.forEach((i) => map.set(i.source, i.source_label));
    return Array.from(map.entries());
  }, [items]);

  const deletedView = view === "deleted";

  const filtered = useMemo(() => {
    const fromT = from ? new Date(from + "T00:00:00").getTime() : null;
    const toT = to ? new Date(to + "T23:59:59").getTime() : null;
    return items.filter((i) => {
      if (source && i.source !== source) return false;
      if (
        q &&
        !`${i.filename} ${i.source_label} ${i.uploaded_by ?? ""} ${i.related.label ?? ""}`
          .toLowerCase()
          .includes(q.toLowerCase())
      )
        return false;
      const stamp = deletedView ? i.deleted_at : i.created_at;
      if (fromT || toT) {
        const t = stamp ? new Date(stamp).getTime() : null;
        if (t === null) return false;
        if (fromT && t < fromT) return false;
        if (toT && t > toT) return false;
      }
      return true;
    });
  }, [items, q, source, from, to, deletedView]);

  const allSelected = filtered.length > 0 && filtered.every((i) => selected.has(i.id));
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(filtered.map((i) => i.id)));
  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const runBulk = async (action: "delete" | "restore" | "permanent") => {
    const ids = filtered.filter((i) => selected.has(i.id)).map((i) => i.id);
    if (ids.length === 0) return;
    setBulkConfirm(null);
    setBulkBusy(true);
    setError(null);
    try {
      await api.bulkArchive(ids, action);
      const done = new Set(ids);
      setItems((prev) => prev.filter((x) => !done.has(x.id)));
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkBusy(false);
    }
  };

  return (
    <div className="space-y-6 animate-in">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Archive</h1>
          <p className="text-sm text-muted">
            Every file attached to the system — for analysis, review or VAT-return processing — is
            stored here automatically and kept unaltered. View, open, and download originals and
            their generated reports anytime.
          </p>
        </div>
        {isAdmin && (
          <div className="flex overflow-hidden rounded-lg border border-border text-sm">
            <button
              onClick={() => switchView("active")}
              className={`px-3 py-1.5 font-medium ${!deletedView ? "bg-brand text-brand-fg" : "text-muted hover:bg-elevated"}`}
            >
              Archived
            </button>
            <button
              onClick={() => switchView("deleted")}
              className={`px-3 py-1.5 font-medium ${deletedView ? "bg-brand text-brand-fg" : "text-muted hover:bg-elevated"}`}
            >
              Recently deleted
            </button>
          </div>
        )}
      </div>

      {deletedView && (
        <Card className="border-warning/40 bg-warning/5 p-3 text-xs text-warning">
          Deleted files are kept here for 30 days, then permanently purged. Restore anytime before
          then, or delete permanently now.
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search filename, source, uploader…"
          className="min-w-[240px] flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
        >
          <option value="">All sources</option>
          {sources.map(([val, label]) => (
            <option key={val} value={val}>
              {label}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-1.5 text-xs text-muted">
          <span>{deletedView ? "Deleted" : "Uploaded"}:</span>
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="rounded-lg border border-border bg-surface px-2 py-2 text-sm"
            title="From date"
          />
          <span>–</span>
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="rounded-lg border border-border bg-surface px-2 py-2 text-sm"
            title="To date"
          />
          {(from || to) && (
            <button
              onClick={() => {
                setFrom("");
                setTo("");
              }}
              className="rounded-lg border border-border px-2 py-2 hover:bg-elevated"
              title="Clear date range"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Bulk action bar (admin) */}
      {isAdmin && selected.size > 0 && (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-brand/40 bg-brand/5 p-3 text-sm">
          <span className="font-medium">{selected.size} selected</span>
          <div className="flex flex-wrap gap-2">
            {deletedView ? (
              <>
                <button
                  onClick={() => runBulk("restore")}
                  disabled={bulkBusy}
                  className="rounded-lg border border-success/40 px-3 py-1.5 text-xs font-medium text-success hover:bg-success/10 disabled:opacity-50"
                >
                  {bulkBusy ? "Working…" : "Restore selected"}
                </button>
                <button
                  onClick={() => setBulkConfirm({ action: "permanent", count: selected.size })}
                  disabled={bulkBusy}
                  className="rounded-lg border border-danger/40 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
                >
                  Delete permanently
                </button>
              </>
            ) : (
              <button
                onClick={() => setBulkConfirm({ action: "delete", count: selected.size })}
                disabled={bulkBusy}
                className="rounded-lg border border-danger/40 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
              >
                {bulkBusy ? "Working…" : "Delete selected"}
              </button>
            )}
            <button
              onClick={() => setSelected(new Set())}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-elevated"
            >
              Clear
            </button>
          </div>
        </Card>
      )}

      {error && (
        <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>
      )}

      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-semibold">{deletedView ? "Recently deleted" : "Archived files"}</h2>
          <span className="rounded-full bg-elevated px-2.5 py-0.5 text-xs text-muted">
            {filtered.length}
            {filtered.length !== items.length ? ` / ${items.length}` : ""}
          </span>
        </div>

        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-muted">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-muted">
            {deletedView
              ? "Nothing in Recently deleted."
              : items.length === 0
                ? "No files archived yet. Upload a document in Document Analysis, Invoice Review, the VAT Assistant, or a VAT Return — it will appear here automatically."
                : "No files match your search."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-elevated text-muted">
                <tr>
                  {isAdmin && (
                    <th className="px-3 py-2 text-left">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleAll}
                        aria-label="Select all"
                        className="align-middle"
                      />
                    </th>
                  )}
                  <th className="px-4 py-2 text-left">File</th>
                  <th className="px-4 py-2 text-left">Source</th>
                  <th className="px-4 py-2 text-left">{deletedView ? "Purges in" : "Related"}</th>
                  <th className="px-4 py-2 text-right">Size</th>
                  <th className="px-4 py-2 text-left">{deletedView ? "Deleted" : "Uploaded"}</th>
                  <th className="px-4 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((i) => (
                  <tr
                    key={i.id}
                    className={`border-t border-border hover:bg-elevated/50 ${selected.has(i.id) ? "bg-brand/5" : ""}`}
                  >
                    {isAdmin && (
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selected.has(i.id)}
                          onChange={() => toggleOne(i.id)}
                          aria-label={`Select ${i.filename}`}
                          className="align-middle"
                        />
                      </td>
                    )}
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        <span>{fileIcon(i.filename)}</span>
                        <a
                          href={api.archiveFileUrl(i.id, false)}
                          target="_blank"
                          rel="noreferrer"
                          className="max-w-[280px] truncate font-medium hover:text-brand"
                          title={i.filename}
                        >
                          {i.filename}
                        </a>
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          SOURCE_STYLE[i.source] ?? "bg-elevated text-muted"
                        }`}
                      >
                        {i.source_label}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      {deletedView ? (
                        <span className="text-xs text-warning">
                          {i.purge_in_days === 0 ? "today" : `${i.purge_in_days} day${i.purge_in_days === 1 ? "" : "s"}`}
                        </span>
                      ) : i.related.analysis_href ? (
                        <Link
                          href={i.related.analysis_href}
                          className="text-xs text-brand hover:underline"
                          title="Open related analysis / details"
                        >
                          {i.related.label ?? "View details"}
                        </Link>
                      ) : (
                        <span className="text-xs text-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right text-muted">{humanSize(i.size_bytes)}</td>
                    <td className="px-4 py-2 text-xs text-muted">
                      <div>
                        {deletedView
                          ? i.deleted_at
                            ? new Date(i.deleted_at).toLocaleString()
                            : "—"
                          : i.created_at
                            ? new Date(i.created_at).toLocaleString()
                            : "—"}
                      </div>
                      {(deletedView ? i.deleted_by : i.uploaded_by) && (
                        <div className="text-[10px]">{deletedView ? i.deleted_by : i.uploaded_by}</div>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex justify-end gap-1.5">
                        <a
                          href={api.archiveFileUrl(i.id, false)}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium hover:bg-elevated"
                          title="Open original file"
                        >
                          Open
                        </a>
                        <a
                          href={api.archiveFileUrl(i.id, true)}
                          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium hover:bg-elevated"
                          title="Download original file"
                        >
                          Download
                        </a>
                        {!deletedView && i.related.report_url && (
                          <a
                            href={api.apiUrl(i.related.report_url)}
                            className="rounded-lg border border-brand bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand hover:bg-brand/20"
                            title="Download the report/analysis generated for this file"
                          >
                            Report
                          </a>
                        )}
                        {isAdmin && !deletedView && (
                          <button
                            onClick={() => setConfirm({ entry: i, permanent: false })}
                            disabled={busyId === i.id}
                            className="rounded-lg border border-danger/40 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
                            title="Move to Recently deleted (recoverable for 30 days)"
                          >
                            {busyId === i.id ? "…" : "Delete"}
                          </button>
                        )}
                        {isAdmin && deletedView && (
                          <>
                            <button
                              onClick={() => restore(i)}
                              disabled={busyId === i.id}
                              className="rounded-lg border border-success/40 px-2.5 py-1 text-xs font-medium text-success hover:bg-success/10 disabled:opacity-50"
                              title="Restore to the archive"
                            >
                              {busyId === i.id ? "…" : "Restore"}
                            </button>
                            <button
                              onClick={() => setConfirm({ entry: i, permanent: true })}
                              disabled={busyId === i.id}
                              className="rounded-lg border border-danger/40 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
                              title="Delete permanently now (cannot be undone)"
                            >
                              Delete permanently
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="text-xs text-muted">
        Archived files are stored as immutable copies — the original is preserved exactly as
        uploaded, independent of any later edits or deletions of the related review or return.
      </p>

      {/* Delete / permanent-delete confirmation */}
      {confirm && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" onClick={() => setConfirm(null)}>
          <Card className="w-full max-w-md p-5">
            <div onClick={(e) => e.stopPropagation()}>
              <h3 className="text-lg font-semibold">
                {confirm.permanent ? "Delete permanently?" : "Delete this file?"}
              </h3>
              <p className="mt-2 text-sm text-muted">
                {confirm.permanent ? (
                  <>
                    <span className="font-medium text-fg">{confirm.entry.filename}</span> and its
                    stored copy will be permanently removed. This cannot be undone.
                  </>
                ) : (
                  <>
                    <span className="font-medium text-fg">{confirm.entry.filename}</span> will move
                    to <b>Recently deleted</b> and stay recoverable for 30 days before it is
                    automatically purged.
                  </>
                )}
              </p>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  onClick={() => setConfirm(null)}
                  className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated"
                >
                  Cancel
                </button>
                <button
                  onClick={doDelete}
                  className="rounded-lg bg-danger px-4 py-2 text-sm font-medium text-white hover:opacity-90"
                >
                  {confirm.permanent ? "Delete permanently" : "Delete"}
                </button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Bulk delete confirmation */}
      {bulkConfirm && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" onClick={() => setBulkConfirm(null)}>
          <Card className="w-full max-w-md p-5">
            <div onClick={(e) => e.stopPropagation()}>
              <h3 className="text-lg font-semibold">
                {bulkConfirm.action === "permanent"
                  ? `Permanently delete ${bulkConfirm.count} file${bulkConfirm.count === 1 ? "" : "s"}?`
                  : `Delete ${bulkConfirm.count} file${bulkConfirm.count === 1 ? "" : "s"}?`}
              </h3>
              <p className="mt-2 text-sm text-muted">
                {bulkConfirm.action === "permanent"
                  ? "The selected files and their stored copies will be permanently removed. This cannot be undone."
                  : "The selected files move to Recently deleted and stay recoverable for 30 days before auto-purge."}
              </p>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  onClick={() => setBulkConfirm(null)}
                  className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated"
                >
                  Cancel
                </button>
                <button
                  onClick={() => runBulk(bulkConfirm.action)}
                  className="rounded-lg bg-danger px-4 py-2 text-sm font-medium text-white hover:opacity-90"
                >
                  {bulkConfirm.action === "permanent" ? "Delete permanently" : "Delete"}
                </button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
