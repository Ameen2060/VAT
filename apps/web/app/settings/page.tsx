"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";
import { Card } from "@/components/ui";

export default function SettingsPage() {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [role, setRole] = useState<string>("");

  useEffect(() => {
    const u = getUser();
    if (u) {
      setEmail(u.email);
      setFullName(u.full_name ?? "");
      setRole(u.role);
    }
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    if (!currentPassword) {
      setError("Enter your current password to confirm changes.");
      return;
    }
    if (newPassword && newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }
    if (newPassword && newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await api.updateAccount({
        current_password: currentPassword,
        new_email: email || undefined,
        new_password: newPassword || undefined,
        full_name: fullName,
      });
      setSaved(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">Account settings</h1>
        <p className="text-sm text-muted">
          Update your login details. Changes take effect immediately; you stay signed in.
        </p>
      </div>

      <Card className="p-6">
        <form onSubmit={submit} className="space-y-5">
          {error && (
            <div className="rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">
              {error}
            </div>
          )}
          {saved && (
            <div className="rounded-lg border border-success/40 bg-success/5 px-3 py-2 text-sm text-success">
              ✓ Your login details were updated.
            </div>
          )}

          <div className="space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Profile</div>
            <label className="block">
              <span className="text-xs font-medium uppercase text-muted">Email (login)</span>
              <input
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium uppercase text-muted">Full name</span>
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
              />
            </label>
            {role && (
              <div className="text-xs text-muted">
                Role: <span className="font-medium uppercase">{role}</span> (only an admin can change roles)
              </div>
            )}
          </div>

          <div className="space-y-4 border-t border-border pt-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">
              Change password <span className="normal-case text-muted">(optional)</span>
            </div>
            <label className="block">
              <span className="text-xs font-medium uppercase text-muted">New password</span>
              <input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Leave blank to keep current password"
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium uppercase text-muted">Confirm new password</span>
              <input
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
              />
            </label>
          </div>

          <div className="space-y-2 border-t border-border pt-5">
            <label className="block">
              <span className="text-xs font-medium uppercase text-muted">
                Current password <span className="text-danger">*</span>
              </span>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="Required to save any change"
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
              />
            </label>
          </div>

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand py-2 text-sm font-medium text-brand-fg hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save changes"}
          </button>
        </form>
      </Card>
    </div>
  );
}
