"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { FtaDashboard } from "@/lib/types";
import { Card } from "@/components/ui";

// Compact "FTA VAT Updates" section for the main dashboard.
export function FtaSummary() {
  const [d, setD] = useState<FtaDashboard | null>(null);

  useEffect(() => {
    api.ftaDashboard().then(setD).catch(() => setD(null));
  }, []);

  if (!d) return null;

  const cells: { label: string; value: number; tone?: string; href: string }[] = [
    { label: "New", value: d.new, tone: "text-brand", href: "/fta-updates?status=new" },
    { label: "Under review", value: d.under_review, tone: "text-warning", href: "/fta-updates?status=under_review" },
    { label: "Approved", value: d.approved, tone: "text-success", href: "/fta-updates?status=approved" },
    { label: "Implemented", value: d.implemented, href: "/fta-updates?status=implemented" },
    { label: "Critical", value: d.critical, tone: "text-danger", href: "/fta-updates?critical=1" },
  ];

  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-semibold">
          FTA VAT Updates
          {d.critical > 0 && (
            <span className="rounded-full bg-danger/15 px-2 py-0.5 text-xs font-semibold text-danger">
              {d.critical} critical
            </span>
          )}
        </h2>
        <Link href="/fta-updates" className="text-xs font-medium text-brand hover:underline">
          Open →
        </Link>
      </div>
      <div className="grid grid-cols-3 gap-3 text-center sm:grid-cols-5">
        {cells.map((c) => (
          <Link
            key={c.label}
            href={c.href}
            title={`View ${c.label.toLowerCase()} updates`}
            className="rounded-lg border border-border py-2 transition-colors hover:border-brand hover:bg-elevated"
          >
            <div className={`text-xl font-semibold ${c.tone ?? ""}`}>{c.value}</div>
            <div className="text-[10px] uppercase text-muted">{c.label}</div>
          </Link>
        ))}
      </div>
      {d.upcoming_effective.length > 0 && (
        <div className="mt-3 text-xs text-muted">
          Next effective: <b>{d.upcoming_effective[0].effective_date}</b> — {d.upcoming_effective[0].title}
        </div>
      )}
    </Card>
  );
}
