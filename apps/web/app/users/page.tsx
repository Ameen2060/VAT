"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getUser, type AuthUser } from "@/lib/auth";
import { Card } from "@/components/ui";

interface AuditRow {
  id: string;
  event: string;
  user_email: string | null;
  actor_email: string | null;
  detail: string | null;
  created_at: string | null;
}

const EVENT_STYLE: Record<string, string> = {
  reset_success: "text-success",
  password_changed: "text-success",
  admin_reset_initiated: "text-brand",
  forgot_request: "text-muted",
  reset_failed: "text-danger",
};

export default function UsersPage() {
  const [isAdmin, setIsAdmin] = useState(true);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [link, setLink] = useState<{ email: string; url: string; mins: number } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setIsAdmin(getUser()?.role === "admin");
    Promise.all([api.listUsers(), api.authAudit()])
      .then(([u, a]) => {
        setUsers(u);
        setAudit(a);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const reset = async (u: AuthUser) => {
    setBusy(u.id);
    setError(null);
    setLink(null);
    try {
      const r = await api.adminResetPassword(u.id);
      setLink({ email: r.user_email, url: r.reset_url, mins: r.expires_minutes });
      setCopied(false);
      api.authAudit().then(setAudit).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!isAdmin) {
    return (
      <Card className="p-6 text-sm text-muted">Administrator access required.</Card>
    );
  }

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">User Management</h1>
        <p className="text-sm text-muted">
          Manage users and initiate a secure password reset without viewing their password.
        </p>
      </div>

      {error && <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>}

      {link && (
        <Card className="border-brand/40 bg-brand/5 p-4 text-sm">
          <div className="font-medium">Reset link generated for {link.email}</div>
          <p className="mt-1 text-xs text-muted">
            Share this one-time link with the user — it expires in {link.mins} minutes. You never see
            their password.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <input readOnly value={link.url}
              className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 font-mono text-xs" />
            <button
              onClick={() => { navigator.clipboard?.writeText(link.url); setCopied(true); }}
              className="rounded-lg border border-border px-3 py-2 text-xs font-medium hover:bg-elevated">
              {copied ? "Copied ✓" : "Copy"}
            </button>
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="border-b border-border px-5 py-4 font-semibold">Users ({users.length})</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-elevated text-muted">
              <tr>
                <th className="px-4 py-2 text-left">Email</th>
                <th className="px-4 py-2 text-left">Name</th>
                <th className="px-4 py-2 text-left">Role</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-border">
                  <td className="px-4 py-2 font-medium">{u.email}</td>
                  <td className="px-4 py-2 text-muted">{u.full_name || "—"}</td>
                  <td className="px-4 py-2">
                    <span className="rounded-full bg-elevated px-2 py-0.5 text-xs font-semibold uppercase">{u.role}</span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button onClick={() => reset(u)} disabled={busy === u.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs font-medium hover:bg-elevated disabled:opacity-50">
                      {busy === u.id ? "…" : "Reset password"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-border px-5 py-4 font-semibold">Security audit — password activity</div>
        {audit.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-muted">No password events recorded yet.</div>
        ) : (
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-elevated text-muted">
                <tr>
                  <th className="px-4 py-2 text-left">Event</th>
                  <th className="px-4 py-2 text-left">User</th>
                  <th className="px-4 py-2 text-left">By</th>
                  <th className="px-4 py-2 text-left">Detail</th>
                  <th className="px-4 py-2 text-left">When</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id} className="border-t border-border">
                    <td className={`px-4 py-1.5 font-medium ${EVENT_STYLE[a.event] ?? ""}`}>{a.event.replace(/_/g, " ")}</td>
                    <td className="px-4 py-1.5 text-xs">{a.user_email || "—"}</td>
                    <td className="px-4 py-1.5 text-xs text-muted">{a.actor_email || "—"}</td>
                    <td className="px-4 py-1.5 text-xs text-muted">{a.detail || "—"}</td>
                    <td className="px-4 py-1.5 text-xs text-muted">{a.created_at ? new Date(a.created_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
