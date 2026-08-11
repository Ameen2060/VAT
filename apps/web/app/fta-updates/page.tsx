"use client";

import { Fragment, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";
import type { FtaDashboard, FtaRule, FtaSource, FtaUpdate, FtaUpdateInput } from "@/lib/types";
import { Card } from "@/components/ui";

const STATUS_ORDER = ["new", "under_review", "approved", "implemented"] as const;
const STATUS_LABEL: Record<string, string> = {
  new: "New",
  under_review: "Under review",
  approved: "Approved",
  implemented: "Implemented",
  rejected: "Rejected",
};
const CLASS_STYLE: Record<string, string> = {
  informational: "bg-elevated text-muted",
  guidance: "bg-warning/15 text-warning",
  legally_effective: "bg-danger/15 text-danger",
};
const SRC_STYLE: Record<string, string> = {
  changed: "bg-warning/15 text-warning",
  unchanged: "bg-success/15 text-success",
  error: "bg-danger/15 text-danger",
  unchecked: "bg-elevated text-muted",
};
const UPDATE_TYPES = [
  "legislation", "executive_regulation", "decision", "public_clarification", "vat_guide",
  "user_guide", "return_requirement", "refund_requirement", "registration_requirement",
  "deregistration_requirement", "rate_change", "treatment_change", "penalty", "procedure",
];

// Allowed workflow transitions surfaced as buttons.
function actionsFor(status: string): { to: string; label: string; tone: string }[] {
  switch (status) {
    case "new":
      return [
        { to: "under_review", label: "Start review", tone: "warning" },
        { to: "rejected", label: "Reject", tone: "danger" },
      ];
    case "under_review":
      return [
        { to: "approved", label: "Approve", tone: "success" },
        { to: "rejected", label: "Reject", tone: "danger" },
      ];
    case "approved":
      return [
        { to: "implemented", label: "Implement + validate", tone: "success" },
        { to: "under_review", label: "Back to review", tone: "muted" },
      ];
    case "rejected":
      return [{ to: "new", label: "Reopen", tone: "brand" }];
    default:
      return [];
  }
}

function Pipeline({ status }: { status: string }) {
  if (status === "rejected")
    return <span className="rounded-full bg-muted/20 px-2 py-0.5 text-xs font-semibold text-muted">Rejected</span>;
  const idx = STATUS_ORDER.indexOf(status as (typeof STATUS_ORDER)[number]);
  return (
    <div className="flex items-center gap-1">
      {STATUS_ORDER.map((s, i) => (
        <span key={s} className="flex items-center gap-1">
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
              i <= idx ? "bg-brand text-brand-fg" : "bg-elevated text-muted"
            }`}
          >
            {STATUS_LABEL[s]}
          </span>
          {i < STATUS_ORDER.length - 1 && <span className="text-muted">→</span>}
        </span>
      ))}
    </div>
  );
}

function Stat({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</div>
    </Card>
  );
}

const EMPTY: FtaUpdateInput = {
  title: "",
  update_type: "public_clarification",
  classification: "informational",
  critical: false,
};

export default function FtaUpdatesPage() {
  const [dash, setDash] = useState<FtaDashboard | null>(null);
  const [updates, setUpdates] = useState<FtaUpdate[]>([]);
  const [sources, setSources] = useState<FtaSource[]>([]);
  const [rules, setRules] = useState<FtaRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FtaUpdateInput>(EMPTY);
  const [tab, setTab] = useState<"log" | "sources" | "rules">("log");
  const isAdmin = typeof window !== "undefined" && getUser()?.role === "admin";

  const refresh = async () => {
    try {
      const [d, u, s, r] = await Promise.all([
        api.ftaDashboard(),
        api.listFtaUpdates(),
        api.listFtaSources(),
        api.listFtaRules(),
      ]);
      setDash(d);
      setUpdates(u);
      setSources(s);
      setRules(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const doTransition = async (id: string, status: string) => {
    setBusy(id);
    setError(null);
    setNotice(null);
    try {
      const u = await api.transitionFtaUpdate(id, status);
      if (status === "implemented" && u.validation) {
        setNotice(
          `Implemented “${u.title}”. Compliance validation: ${u.validation.passed}/${u.validation.total} checks passed.`,
        );
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const doDelete = async (id: string) => {
    setBusy(id);
    try {
      await api.deleteFtaUpdate(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const checkSources = async () => {
    setBusy("check");
    setNotice(null);
    setError(null);
    try {
      const r = await api.checkFtaSources();
      setNotice(
        `Checked ${r.checked} official sources — ${r.changed} changed (logged as new signals), ${r.errors} unreachable.`,
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const seed = async () => {
    setBusy("seed");
    try {
      await api.seedFta();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    setBusy("create");
    try {
      await api.createFtaUpdate(form);
      setShowForm(false);
      setForm(EMPTY);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">FTA VAT Regulatory Updates</h1>
        <p className="text-sm text-muted">
          Monitors official UAE FTA &amp; Ministry of Finance sources for VAT changes and tracks
          them through <b>New → Under review → Approved → Implemented</b>. A detected page change is
          only an <i>informational signal</i> — nothing is applied to the live VAT engine without
          authorised approval.
        </p>
      </div>

      {error && <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>}
      {notice && <Card className="border-success/40 bg-success/5 p-4 text-sm text-success">{notice}</Card>}

      {/* Dashboard */}
      {dash && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Stat label="New" value={dash.new} tone="text-brand" />
          <Stat label="Under review" value={dash.under_review} tone="text-warning" />
          <Stat label="Approved" value={dash.approved} tone="text-success" />
          <Stat label="Implemented" value={dash.implemented} />
          <Stat label="Critical (pending)" value={dash.critical} tone="text-danger" />
        </div>
      )}

      {/* Upcoming effective dates */}
      {dash && dash.upcoming_effective.length > 0 && (
        <Card className="p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Upcoming effective dates</div>
          <ul className="mt-2 space-y-1 text-sm">
            {dash.upcoming_effective.map((u) => (
              <li key={u.id} className="flex items-center gap-2">
                <span className="rounded bg-elevated px-2 py-0.5 text-xs font-medium">{u.effective_date}</span>
                {u.critical && <span className="text-xs text-danger">● critical</span>}
                <span className="truncate">{u.title}</span>
                {u.affected_module && <span className="text-xs text-muted">· {u.affected_module}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Action bar */}
      {isAdmin && (
        <div className="flex flex-wrap gap-2">
          <button onClick={checkSources} disabled={busy === "check"}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg hover:opacity-90 disabled:opacity-50">
            {busy === "check" ? "Checking…" : "Check sources now"}
          </button>
          <button onClick={() => setShowForm(true)}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated">
            + Log an update
          </button>
          {sources.length === 0 && (
            <button onClick={seed} disabled={busy === "seed"}
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated disabled:opacity-50">
              {busy === "seed" ? "Seeding…" : "Load official sources & baseline rules"}
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border text-sm">
        {([["log", "Change log"], ["sources", `Monitored sources (${sources.length})`], ["rules", `Rule registry (${rules.length})`]] as const).map(
          ([t, label]) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 font-medium ${tab === t ? "border-b-2 border-brand text-fg" : "text-muted"}`}>
              {label}
            </button>
          ),
        )}
      </div>

      {/* Change log */}
      {tab === "log" && (
        <Card className="overflow-hidden">
          {updates.length === 0 ? (
            <div className="px-5 py-12 text-center text-sm text-muted">
              No regulatory updates logged yet. {isAdmin ? "Use “Check sources now” to scan official pages, or “Log an update” to record a change manually." : ""}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-elevated text-muted">
                  <tr>
                    <th className="px-4 py-2 text-left">Update</th>
                    <th className="px-4 py-2 text-left">Class</th>
                    <th className="px-4 py-2 text-left">Status</th>
                    <th className="px-4 py-2 text-left">Effective</th>
                    <th className="px-4 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {updates.map((u) => (
                    <Fragment key={u.id}>
                      <tr className="border-t border-border align-top hover:bg-elevated/40">
                        <td className="px-4 py-2">
                          <button onClick={() => setExpanded(expanded === u.id ? null : u.id)} className="text-left">
                            <div className="flex items-center gap-2 font-medium">
                              {u.critical && <span className="text-danger" title="Critical">●</span>}
                              <span className="max-w-[360px] truncate">{u.title}</span>
                            </div>
                            <div className="text-xs text-muted">
                              {u.update_type.replace(/_/g, " ")} · {u.publication_date ?? "—"}
                              {u.affected_module ? ` · ${u.affected_module}` : ""}
                            </div>
                          </button>
                        </td>
                        <td className="px-4 py-2">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CLASS_STYLE[u.classification] ?? "bg-elevated text-muted"}`}>
                            {u.classification.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="px-4 py-2"><Pipeline status={u.status} /></td>
                        <td className="px-4 py-2 text-xs">{u.effective_date ?? "—"}</td>
                        <td className="px-4 py-2">
                          <div className="flex flex-wrap justify-end gap-1.5">
                            {isAdmin &&
                              actionsFor(u.status).map((a) => (
                                <button key={a.to} onClick={() => doTransition(u.id, a.to)} disabled={busy === u.id}
                                  className={`rounded-lg border px-2.5 py-1 text-xs font-medium disabled:opacity-50 ${
                                    a.tone === "success" ? "border-success/40 text-success hover:bg-success/10"
                                    : a.tone === "danger" ? "border-danger/40 text-danger hover:bg-danger/10"
                                    : a.tone === "warning" ? "border-warning/40 text-warning hover:bg-warning/10"
                                    : "border-border hover:bg-elevated"
                                  }`}>
                                  {a.label}
                                </button>
                              ))}
                            {isAdmin && (
                              <button onClick={() => doDelete(u.id)} disabled={busy === u.id}
                                className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted hover:text-danger disabled:opacity-50">
                                ✕
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                      {expanded === u.id && (
                        <tr className="border-t border-border bg-elevated/30">
                          <td colSpan={5} className="px-4 py-3">
                            <div className="grid gap-3 sm:grid-cols-2">
                              <div>
                                <div className="text-[10px] font-semibold uppercase text-muted">Previous rule</div>
                                <p className="text-sm">{u.previous_rule || "—"}</p>
                              </div>
                              <div>
                                <div className="text-[10px] font-semibold uppercase text-muted">New rule</div>
                                <p className="text-sm">{u.new_rule || "—"}</p>
                              </div>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                              {u.affected_treatment && <span>Treatment: <b>{u.affected_treatment}</b></span>}
                              {u.approved_by && <span>Approved by: {u.approved_by}</span>}
                              {u.implemented_at && <span>Implemented: {new Date(u.implemented_at).toLocaleString()}</span>}
                              {u.source_ref && (
                                <a href={u.source_ref} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                                  Source ↗
                                </a>
                              )}
                            </div>
                            {u.validation && (
                              <div className="mt-3 rounded-lg border border-border p-3">
                                <div className="text-xs font-semibold">
                                  Post-implementation validation: {u.validation.passed}/{u.validation.total} passed
                                  {u.validation.ok ? " ✓" : " ✕"}
                                </div>
                                <div className="mt-1 grid gap-x-4 gap-y-0.5 text-xs text-muted sm:grid-cols-2">
                                  {u.validation.checks.map((c, i) => (
                                    <div key={i}>
                                      <span className={c.passed ? "text-success" : "text-danger"}>{c.passed ? "✓" : "✕"}</span>{" "}
                                      {c.category}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Monitored sources */}
      {tab === "sources" && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-elevated text-muted">
                <tr>
                  <th className="px-4 py-2 text-left">Source</th>
                  <th className="px-4 py-2 text-left">Authority</th>
                  <th className="px-4 py-2 text-left">Category</th>
                  <th className="px-4 py-2 text-left">Last status</th>
                  <th className="px-4 py-2 text-left">Checked</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <a href={s.url} target="_blank" rel="noreferrer" className="font-medium hover:text-brand">{s.name}</a>
                      {s.note && <div className="text-[10px] text-danger">{s.note}</div>}
                    </td>
                    <td className="px-4 py-2 text-xs">{s.authority}</td>
                    <td className="px-4 py-2 text-xs">{s.category}</td>
                    <td className="px-4 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SRC_STYLE[s.last_status] ?? "bg-elevated text-muted"}`}>
                        {s.last_status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-xs text-muted">
                      {s.last_checked_at ? new Date(s.last_checked_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
                {sources.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-muted">No sources configured.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Rule registry */}
      {tab === "rules" && (
        <Card className="overflow-hidden">
          <div className="border-b border-border px-4 py-2 text-xs text-muted">
            Every VAT treatment the engine applies is backed by a cited, effective-dated rule — so
            transactions are computed under the rule in force on their date (historical protection).
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-elevated text-muted">
                <tr>
                  <th className="px-4 py-2 text-left">Rule</th>
                  <th className="px-4 py-2 text-left">Value</th>
                  <th className="px-4 py-2 text-left">Effective</th>
                  <th className="px-4 py-2 text-left">Source</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id} className="border-t border-border align-top">
                    <td className="px-4 py-2">
                      <div className="font-medium">{r.title}</div>
                      <div className="text-[10px] text-muted">{r.rule_key}</div>
                    </td>
                    <td className="px-4 py-2 text-xs">{r.value}</td>
                    <td className="px-4 py-2 text-xs">
                      {r.effective_from} → {r.effective_to ?? "current"}
                    </td>
                    <td className="px-4 py-2 text-xs text-brand">{r.source_ref}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Add-update form */}
      {showForm && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowForm(false)}>
          <Card className="max-h-[85vh] w-full max-w-2xl overflow-auto p-5" >
            <div onClick={(e) => e.stopPropagation()}>
              <h3 className="text-lg font-semibold">Log a regulatory update</h3>
              <form onSubmit={submitForm} className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="block sm:col-span-2">
                  <span className="text-xs uppercase text-muted">Title *</span>
                  <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Type</span>
                  <select value={form.update_type} onChange={(e) => setForm({ ...form, update_type: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                    {UPDATE_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                  </select>
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Legal classification</span>
                  <select value={form.classification} onChange={(e) => setForm({ ...form, classification: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                    <option value="informational">Informational</option>
                    <option value="guidance">Guidance</option>
                    <option value="legally_effective">Legally effective</option>
                  </select>
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Publication date</span>
                  <input type="date" value={form.publication_date ?? ""} onChange={(e) => setForm({ ...form, publication_date: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Effective date</span>
                  <input type="date" value={form.effective_date ?? ""} onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Affected module</span>
                  <input value={form.affected_module ?? ""} onChange={(e) => setForm({ ...form, affected_module: e.target.value })}
                    placeholder="e.g. VAT Return, Reverse charge"
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Affected treatment</span>
                  <input value={form.affected_treatment ?? ""} onChange={(e) => setForm({ ...form, affected_treatment: e.target.value })}
                    placeholder="e.g. zero_rated"
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="block sm:col-span-2">
                  <span className="text-xs uppercase text-muted">Source / reference (official URL or citation)</span>
                  <input value={form.source_ref ?? ""} onChange={(e) => setForm({ ...form, source_ref: e.target.value })}
                    placeholder="https://tax.gov.ae/…"
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Previous rule</span>
                  <textarea value={form.previous_rule ?? ""} onChange={(e) => setForm({ ...form, previous_rule: e.target.value })} rows={3}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">New rule</span>
                  <textarea value={form.new_rule ?? ""} onChange={(e) => setForm({ ...form, new_rule: e.target.value })} rows={3}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
                </label>
                <label className="flex items-center gap-2 text-sm sm:col-span-2">
                  <input type="checkbox" checked={!!form.critical} onChange={(e) => setForm({ ...form, critical: e.target.checked })} />
                  Mark as critical
                </label>
                <div className="flex justify-end gap-2 sm:col-span-2">
                  <button type="button" onClick={() => setShowForm(false)}
                    className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated">Cancel</button>
                  <button type="submit" disabled={busy === "create"}
                    className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50">
                    {busy === "create" ? "Saving…" : "Log update (as New)"}
                  </button>
                </div>
              </form>
            </div>
          </Card>
        </div>
      )}

      <p className="text-xs text-muted">
        Regulatory information is labelled Informational / Guidance / Legally effective and progresses
        through an explicit review workflow. Unverified interpretations are never presented as
        confirmed UAE VAT law — always confirm against the official FTA source before relying on a change.
      </p>
    </div>
  );
}
