"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

// Client-side mirror of the server's strong-password policy.
const RULES: { label: string; test: (p: string) => boolean }[] = [
  { label: "At least 8 characters", test: (p) => p.length >= 8 },
  { label: "A lower-case letter", test: (p) => /[a-z]/.test(p) },
  { label: "An upper-case letter", test: (p) => /[A-Z]/.test(p) },
  { label: "A number", test: (p) => /\d/.test(p) },
];

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("token");
    setToken(t);
  }, []);

  const strong = RULES.every((r) => r.test(pw));
  const match = pw.length > 0 && pw === confirm;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (!strong) {
      setError("Please meet all password requirements.");
      return;
    }
    if (!match) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword(token, pw);
      setDone(true);
      setTimeout(() => router.replace("/"), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand text-lg font-bold text-brand-fg">V</div>
          <div>
            <div className="text-lg font-semibold">UAE VAT Compliance</div>
            <div className="text-xs text-muted">Set a new password</div>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-6 shadow-card">
          {done ? (
            <div className="space-y-3 text-center">
              <div className="rounded-lg border border-success/40 bg-success/5 px-3 py-3 text-sm text-success">
                ✓ Your password has been reset. Signing you in…
              </div>
            </div>
          ) : !token ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">
                This reset link is missing or invalid. Request a new one from the sign-in page.
              </div>
              <Link href="/login" className="block text-center text-xs text-brand hover:underline">← Back to sign in</Link>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              {error && (
                <div className="rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</div>
              )}
              <label className="block">
                <span className="text-xs font-medium uppercase text-muted">New password</span>
                <input type="password" autoComplete="new-password" required value={pw}
                  onChange={(e) => setPw(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand" />
              </label>
              <ul className="space-y-0.5 text-xs">
                {RULES.map((r) => {
                  const ok = r.test(pw);
                  return (
                    <li key={r.label} className={ok ? "text-success" : "text-muted"}>
                      {ok ? "✓" : "○"} {r.label}
                    </li>
                  );
                })}
              </ul>
              <label className="block">
                <span className="text-xs font-medium uppercase text-muted">Confirm new password</span>
                <input type="password" autoComplete="new-password" required value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand" />
                {confirm.length > 0 && !match && <span className="mt-1 block text-[11px] text-danger">Passwords do not match.</span>}
              </label>
              <button type="submit" disabled={busy || !strong || !match}
                className="w-full rounded-lg bg-brand py-2 text-sm font-medium text-brand-fg hover:opacity-90 disabled:opacity-50">
                {busy ? "Resetting…" : "Reset password"}
              </button>
              <Link href="/login" className="block text-center text-xs text-brand hover:underline">← Back to sign in</Link>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
