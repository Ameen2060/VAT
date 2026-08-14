"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { VatCode } from "@/lib/types";
import { getUser } from "@/lib/auth";
import { Card } from "@/components/ui";

export default function VatCodesPage() {
  const [codes, setCodes] = useState<VatCode[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savingCode, setSavingCode] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, Partial<VatCode>>>({});
  const isAdmin = getUser()?.role === "admin";

  useEffect(() => {
    api.listVatCodes().then(setCodes).catch((e) => setError(String(e.message ?? e)));
  }, []);

  const setField = (code: string, field: keyof VatCode, value: string | boolean) =>
    setEdits((p) => ({ ...p, [code]: { ...p[code], [field]: value } }));

  const val = (c: VatCode, field: keyof VatCode) =>
    (edits[c.code]?.[field] ?? c[field] ?? "") as string;

  const save = async (c: VatCode) => {
    const patch = edits[c.code];
    if (!patch) return;
    setSavingCode(c.code);
    try {
      const updated = await api.updateVatCode(c.code, patch);
      setCodes((prev) => prev.map((x) => (x.code === c.code ? updated : x)));
      setEdits((p) => {
        const n = { ...p };
        delete n[c.code];
        return n;
      });
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setSavingCode(null);
    }
  };

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">VAT Tax-Code Master</h1>
        <p className="text-sm text-muted">
          The central UAE VAT treatment master — standard, zero-rated, exempt, out-of-scope,
          reverse charge, GCC and adjustments. The Document Analysis engine reads rates and names
          from here. {isAdmin ? "Edit and save any row." : "Read-only (admin edits)."}
        </p>
      </div>

      {error && <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>}

      <div className="space-y-3">
        {codes.map((c) => {
          const dirty = !!edits[c.code];
          return (
            <Card key={c.code} className="p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-brand px-2 py-1 text-sm font-bold text-brand-fg">{c.code}</span>
                <input
                  className="min-w-[180px] flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm disabled:opacity-70"
                  value={val(c, "name")}
                  disabled={!isAdmin}
                  onChange={(e) => setField(c.code, "name", e.target.value)}
                />
                <label className="flex items-center gap-1.5 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={(edits[c.code]?.active ?? c.active) as boolean}
                    disabled={!isAdmin}
                    onChange={(e) => setField(c.code, "active", e.target.checked)}
                  />
                  Active
                </label>
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Labeled label="VAT rate">
                  <input
                    className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm disabled:opacity-70"
                    value={val(c, "rate")}
                    placeholder="N/A"
                    disabled={!isAdmin}
                    onChange={(e) => setField(c.code, "rate", e.target.value)}
                  />
                </Labeled>
                <Labeled label="VAT return box">
                  <input
                    className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm disabled:opacity-70"
                    value={val(c, "vat_return_box")}
                    disabled={!isAdmin}
                    onChange={(e) => setField(c.code, "vat_return_box", e.target.value)}
                  />
                </Labeled>
                <Labeled label="Effective from">
                  <input
                    className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm disabled:opacity-70"
                    value={val(c, "effective_from")}
                    placeholder="YYYY-MM-DD"
                    disabled={!isAdmin}
                    onChange={(e) => setField(c.code, "effective_from", e.target.value)}
                  />
                </Labeled>
                <Labeled label="Effective to">
                  <input
                    className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm disabled:opacity-70"
                    value={val(c, "effective_to")}
                    placeholder="(open)"
                    disabled={!isAdmin}
                    onChange={(e) => setField(c.code, "effective_to", e.target.value)}
                  />
                </Labeled>
              </div>

              <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted">
                {c.reverse_charge && <Tag>Reverse charge</Tag>}
                {c.zero_rated && <Tag>Zero-rated</Tag>}
                {c.exempt && <Tag>Exempt</Tag>}
                {c.out_of_scope && <Tag>Out of scope</Tag>}
                {c.adjustment && <Tag>Adjustment</Tag>}
                <span className="ml-auto">{c.regulatory_ref}</span>
              </div>

              {isAdmin && (
                <div className="mt-3 flex justify-end">
                  <button
                    onClick={() => save(c)}
                    disabled={!dirty || savingCode === c.code}
                    className="rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-brand-fg disabled:opacity-40"
                  >
                    {savingCode === c.code ? "Saving…" : "Save"}
                  </button>
                </div>
              )}
            </Card>
          );
        })}
        {codes.length === 0 && !error && (
          <Card className="px-5 py-12 text-center text-sm text-muted">Loading tax codes…</Card>
        )}
      </div>
    </div>
  );
}

function Labeled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-border px-2 py-0.5">{children}</span>;
}
