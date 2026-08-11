"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { clearSession, getUser, isAuthenticated } from "@/lib/auth";
import type { AiStatus } from "@/lib/types";
import { useTheme } from "./theme-provider";

const NAV = [
  { href: "/", label: "Dashboard", icon: "grid" },
  { href: "/analyze", label: "Document Analysis", icon: "scan" },
  { href: "/assistant", label: "VAT Assistant", icon: "chat" },
  { href: "/vat-return", label: "VAT Return", icon: "receipt" },
  { href: "/fta-updates", label: "FTA Updates", icon: "bell" },
  { href: "/knowledge", label: "Knowledge Base", icon: "book" },
  { href: "/repository", label: "Repository", icon: "folder" },
  { href: "/archive", label: "Archive", icon: "archive" },
];

function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
    doc: "M6 2h9l5 5v15H6zM14 2v6h6",
    chat: "M4 4h16v11H8l-4 4z",
    folder: "M3 6h6l2 2h10v11H3z",
    book: "M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM19 3v16",
    scan: "M4 7V4h3M17 4h3v3M20 17v3h-3M7 20H4v-3M4 12h16",
    receipt: "M5 3v18l2-1 2 1 2-1 2 1 2-1 2 1V3l-2 1-2-1-2 1-2-1-2 1zM8 8h8M8 12h8",
    sun: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66 5.66l1.41 1.41M4.93 4.93l1.41 1.41m0 12.72l-1.41 1.41M19.07 4.93l-1.41 1.41M12 8a4 4 0 100 8 4 4 0 000-8z",
    moon: "M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z",
    gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 13a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z",
    archive: "M3 4h18v4H3zM5 8v12h14V8M9 12h6",
    bell: "M18 8a6 6 0 00-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0",
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d={paths[name]} />
    </svg>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggle } = useTheme();
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [ready, setReady] = useState(false);

  // Auth gate: unauthenticated users are sent to /login (client-side).
  useEffect(() => {
    if (pathname === "/login") {
      setReady(true);
      return;
    }
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [pathname, router]);

  useEffect(() => {
    if (pathname === "/login" || !isAuthenticated()) return;
    api.aiStatus().then(setAi).catch(() => setAi(null));
  }, [pathname]);

  // The login page renders without the app chrome.
  if (pathname === "/login") return <>{children}</>;
  if (!ready) return null;

  const user = getUser();
  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-surface md:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-brand-fg font-bold">
            V
          </div>
          <div className="leading-tight">
            <div className="font-semibold">VAT Compliance</div>
            <div className="text-xs text-muted">UAE · FTA</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-2">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-brand text-brand-fg"
                    : "text-muted hover:bg-elevated hover:text-fg"
                }`}
              >
                <Icon name={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border px-4 py-3 text-xs text-muted">
          Grounded in Federal Decree-Law No. 8 of 2017
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface/80 px-6 py-3 backdrop-blur">
          <div className="text-sm text-muted">UAE VAT Compliance Platform</div>
          <div className="flex items-center gap-3">
            {ai && (
              <span
                title={ai.message}
                className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium sm:inline-flex ${
                  ai.ready
                    ? "border-success/40 text-success"
                    : ai.using_llm
                      ? "border-warning/40 text-warning"
                      : "border-border text-muted"
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${ai.ready ? "bg-success" : "bg-muted"}`} />
                {ai.ready ? `AI: ${ai.active_provider}` : "AI: offline mode"}
              </span>
            )}
            <button
              onClick={toggle}
              aria-label="Toggle theme"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted hover:text-fg"
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} />
            </button>
            {user && (
              <div className="flex items-center gap-2 border-l border-border pl-3">
                <Link href="/settings" className="hidden text-right sm:block hover:opacity-80" title="Account settings">
                  <div className="text-xs font-medium">{user.email}</div>
                  <div className="text-[10px] uppercase text-muted">{user.role}</div>
                </Link>
                <Link
                  href="/settings"
                  aria-label="Account settings"
                  title="Account settings"
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted hover:text-fg"
                >
                  <Icon name="gear" />
                </Link>
                <button
                  onClick={logout}
                  className="rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-muted hover:text-fg"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
