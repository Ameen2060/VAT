"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "forgot">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<{ message: string; reset_url: string | null } | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(email, password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const sendReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setSent(await api.forgotPassword(email));
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
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand text-lg font-bold text-brand-fg">
            V
          </div>
          <div>
            <div className="text-lg font-semibold">UAE VAT Compliance</div>
            <div className="text-xs text-muted">
              {mode === "login" ? "Sign in to continue" : "Reset your password"}
            </div>
          </div>
        </div>

        {mode === "login" ? (
          <form onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-surface p-6 shadow-card">
            {error && (
              <div className="rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</div>
            )}
            <label className="block">
              <span className="text-xs font-medium uppercase text-muted">Email</span>
              <input type="email" autoComplete="username" required value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand" />
            </label>
            <label className="block">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase text-muted">Password</span>
                <button type="button" onClick={() => { setMode("forgot"); setError(null); setSent(null); }}
                  className="text-xs text-brand hover:underline">
                  Forgot password?
                </button>
              </div>
              <input type="password" autoComplete="current-password" required value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand" />
            </label>
            <button type="submit" disabled={busy}
              className="w-full rounded-lg bg-brand py-2 text-sm font-medium text-brand-fg hover:opacity-90 disabled:opacity-50">
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : (
          <form onSubmit={sendReset} className="space-y-4 rounded-xl border border-border bg-surface p-6 shadow-card">
            {error && (
              <div className="rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</div>
            )}
            {sent ? (
              <div className="space-y-3">
                <div className="rounded-lg border border-success/40 bg-success/5 px-3 py-2 text-sm text-success">
                  {sent.message}
                </div>
                {sent.reset_url && (
                  <div className="rounded-lg border border-border bg-elevated px-3 py-2 text-xs">
                    <div className="mb-1 font-medium">Demo mode (no email configured):</div>
                    <Link href={sent.reset_url.replace(/^https?:\/\/[^/]+/, "")} className="break-all text-brand hover:underline">
                      Reset your password now →
                    </Link>
                  </div>
                )}
              </div>
            ) : (
              <>
                <p className="text-sm text-muted">
                  Enter your registered email and we&apos;ll send a secure password-reset link.
                </p>
                <label className="block">
                  <span className="text-xs font-medium uppercase text-muted">Email</span>
                  <input type="email" autoComplete="username" required value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand" />
                </label>
                <button type="submit" disabled={busy}
                  className="w-full rounded-lg bg-brand py-2 text-sm font-medium text-brand-fg hover:opacity-90 disabled:opacity-50">
                  {busy ? "Sending…" : "Send reset link"}
                </button>
              </>
            )}
            <button type="button" onClick={() => { setMode("login"); setError(null); setSent(null); }}
              className="w-full text-center text-xs text-brand hover:underline">
              ← Back to sign in
            </button>
          </form>
        )}

        <p className="mt-4 text-center text-xs text-muted">
          Access is restricted. Contact your administrator for an account.
        </p>
      </div>
    </div>
  );
}
