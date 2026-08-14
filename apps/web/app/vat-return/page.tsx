"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Vat201Return, Vat201Txn, Vat311Application } from "@/lib/types";
import { Card } from "@/components/ui";

const TOTAL_BOXES = new Set(["8", "11", "12", "13", "14"]);

function Tile({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${tone}`}>{value}</div>
    </Card>
  );
}

function money(v: string | undefined) {
  const n = Number(v ?? 0);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function VatReturnPage() {
  const [file, setFile] = useState<File | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [companyTrn, setCompanyTrn] = useState("");
  const [periodType, setPeriodType] = useState("quarter");
  const [year, setYear] = useState(2026);
  const [index, setIndex] = useState(3);
  const [filterByDate, setFilterByDate] = useState(true);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<{ id: string; ret: Vat201Return } | null>(null);
  const [drill, setDrill] = useState<{ box: string; label: string; txns: Vat201Txn[] } | null>(null);

  // VAT311 refund application
  const [refundAmount, setRefundAmount] = useState("");
  const [refundPenalty, setRefundPenalty] = useState("0");
  const [refundLegalName, setRefundLegalName] = useState("");
  const [refundSignatory, setRefundSignatory] = useState("");
  const [refundApp, setRefundApp] = useState<Vat311Application | null>(null);
  const [refundBusy, setRefundBusy] = useState(false);

  const resetRefund = (r: Vat201Return) => {
    setRefundApp(null);
    setRefundAmount(r.totals.net_vat_due);
    setRefundLegalName(r.company_name || "");
    setRefundPenalty("0");
  };

  const generate = async () => {
    if (!file) {
      setError("Choose a CSV or Excel transactions file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.generateVat201(file, {
        company_name: companyName,
        company_trn: companyTrn,
        period_type: periodType,
        year,
        index,
        filter_by_date: filterByDate,
      });
      setCurrent({ id: res.id, ret: res.return });
      setDrill(null);
      resetRefund(res.return);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const openBox = async (box: string, label: string) => {
    if (!current) return;
    const txns = await api.vat201DrillDown(current.id, box);
    setDrill({ box, label, txns });
  };

  const prepareRefund = async () => {
    if (!current) return;
    setRefundBusy(true);
    setError(null);
    try {
      const app = await api.prepareRefund311(current.id, {
        amount_requested: Number(refundAmount),
        late_registration_penalty: Number(refundPenalty || 0),
        legal_name: refundLegalName || undefined,
        authorized_signatory: refundSignatory || undefined,
      });
      setRefundApp(app);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefundBusy(false);
    }
  };

  const ret = current?.ret;
  const totals = ret?.totals;
  const maxIndex = periodType === "month" ? 12 : 4;

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl font-semibold">VAT Return (VAT201)</h1>
        <p className="text-sm text-muted">
          Upload your period&apos;s transactions (CSV/Excel); the system classifies each into the
          FTA VAT201 boxes and computes the return. Columns are auto-detected — no fixed template.
        </p>
      </div>

      {/* Setup */}
      <Card className="p-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block sm:col-span-2">
            <span className="text-xs uppercase text-muted">
              Transactions file (any type — Excel, CSV, TXT; format auto-detected)
            </span>
            <input
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm"
            />
          </label>
          <label className="block">
            <span className="text-xs uppercase text-muted">Company name</span>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand" />
          </label>
          <label className="block">
            <span className="text-xs uppercase text-muted">Company TRN</span>
            <input value={companyTrn} onChange={(e) => setCompanyTrn(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand" />
          </label>
          <label className="block">
            <span className="text-xs uppercase text-muted">Period</span>
            <select value={periodType} onChange={(e) => { setPeriodType(e.target.value); setIndex(1); }}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm">
              <option value="quarter">Quarterly</option>
              <option value="month">Monthly</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase text-muted">Year</span>
            <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand" />
          </label>
          <label className="block">
            <span className="text-xs uppercase text-muted">{periodType === "month" ? "Month" : "Quarter"}</span>
            <select value={index} onChange={(e) => setIndex(Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm">
              {Array.from({ length: maxIndex }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>{periodType === "month" ? `Month ${n}` : `Q${n}`}</option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button onClick={generate} disabled={busy}
              className="w-full rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50">
              {busy ? "Generating…" : "Generate VAT201"}
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-muted">
          Box 1 splits by Emirate automatically when your file has an <b>Emirate</b> column;
          otherwise standard-rated sales are reported under Dubai (Box 1b).
        </p>
        <label className="mt-3 flex items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={filterByDate} onChange={(e) => setFilterByDate(e.target.checked)} />
          Filter transactions to the selected period by date. Uncheck when the file already
          contains exactly this period&apos;s rows (e.g. a prepared workbook or a staggered quarter
          like Jun–Aug).
        </label>
        {error && <div className="mt-3 rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</div>}
      </Card>

      {ret && totals && (
        <>
          {/* Dashboard tiles */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Tile label="Output VAT" value={money(totals.output_vat)} />
            <Tile label="Recoverable input VAT" value={money(totals.recoverable_input_vat)} />
            <Tile label="Reverse-charge VAT" value={money(totals.reverse_charge_vat)} />
            <Tile
              label={totals.is_refund ? "Net VAT refundable" : "Net VAT payable"}
              value={money(totals.net_vat_due)}
              tone={totals.is_refund ? "text-success" : "text-danger"}
            />
          </div>

          <Card className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
            <div>
              <span className="font-semibold">{ret.company_name || "—"}</span>
              <span className="text-muted"> · TRN {ret.company_trn || "—"}</span>
              <span className="text-muted"> · Period {ret.period_label} ({ret.period_start} → {ret.period_end})</span>
              <span className="text-muted"> · Due {ret.due_date}</span>
              <span className="text-muted"> · {ret.transaction_count} txns</span>
            </div>
            <div className="flex gap-2">
              {([["csv", "Export CSV"], ["xlsx", "Export Excel"], ["pdf", "Export PDF"]] as const).map(
                ([f, label]) => (
                  <a key={f} href={api.vat201ExportUrl(current!.id, f)}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-elevated">
                    {label}
                  </a>
                ),
              )}
              <a href={api.vat201FafUrl(current!.id)}
                title="FTA VAT Audit File — Required information, VAT Return summary and a transaction listing per box"
                className="rounded-lg border border-brand bg-brand/10 px-3 py-1.5 text-xs font-semibold text-brand hover:bg-brand/20">
                Generate FAF (Audit File)
              </a>
            </div>
          </Card>

          {/* Validation */}
          {ret.validations.length > 0 && (
            <Card className="p-5">
              <h2 className="font-semibold">Validation ({ret.validations.length})</h2>
              <ul className="mt-2 space-y-1 text-sm">
                {ret.validations.map((v, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className={v.severity === "error" ? "text-danger" : "text-warning"}>
                      {v.severity === "error" ? "✕" : "!"}
                    </span>
                    <span>
                      {v.message}
                      {v.invoice_number ? ` (${v.invoice_number})` : v.row_index ? ` (row ${v.row_index})` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {/* VAT201 boxes */}
          <Card className="overflow-hidden">
            <div className="border-b border-border px-5 py-4 font-semibold">VAT201 Boxes — click a box to drill down</div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-elevated text-muted">
                  <tr>
                    <th className="px-4 py-2 text-left">Box</th>
                    <th className="px-4 py-2 text-left">Description</th>
                    <th className="px-4 py-2 text-right">Amount (AED)</th>
                    <th className="px-4 py-2 text-right">VAT (AED)</th>
                  </tr>
                </thead>
                <tbody>
                  {ret.boxes.map((b) => (
                    <tr
                      key={b.box}
                      onClick={() => b.count > 0 && openBox(b.box, b.label)}
                      className={`border-t border-border ${TOTAL_BOXES.has(b.box) ? "bg-elevated/60 font-semibold" : ""} ${b.count > 0 ? "cursor-pointer hover:bg-elevated" : ""}`}
                    >
                      <td className="px-4 py-2">{b.box}</td>
                      <td className="px-4 py-2">
                        {b.label}
                        {b.count > 0 && <span className="ml-2 text-xs text-brand">({b.count})</span>}
                      </td>
                      <td className="px-4 py-2 text-right">{money(b.amount)}</td>
                      <td className="px-4 py-2 text-right">{money(b.vat)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* VAT311 refund application — only when the return is refundable */}
          {totals.is_refund && (
            <Card className="border-brand/30 p-5">
              <div className="flex items-center gap-2">
                <h2 className="font-semibold">VAT Refund Application (VAT311)</h2>
                <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs font-semibold text-success">
                  Refundable
                </span>
              </div>
              <p className="mt-1 text-xs text-muted">
                This return is in a refund position. Prepare the FTA <b>VAT311</b> refund request,
                then download it for submission on EmaraTax.
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <label className="block">
                  <span className="text-xs uppercase text-muted">Legal name of entity</span>
                  <input value={refundLegalName} onChange={(e) => setRefundLegalName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand" />
                </label>
                <div>
                  <span className="text-xs uppercase text-muted">Total excess refundable (AED)</span>
                  <div className="mt-1 py-1.5 text-sm font-semibold">{money(totals.net_vat_due)}</div>
                </div>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Amount to request (AED)</span>
                  <input value={refundAmount} onChange={(e) => setRefundAmount(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Late registration penalty (AED)</span>
                  <input value={refundPenalty} onChange={(e) => setRefundPenalty(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase text-muted">Authorized signatory</span>
                  <input value={refundSignatory} onChange={(e) => setRefundSignatory(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-brand" />
                </label>
                <div>
                  <span className="text-xs uppercase text-muted">Remaining (carry forward)</span>
                  <div className="mt-1 py-1.5 text-sm font-semibold">
                    {money(String(Number(totals.net_vat_due) - Number(refundAmount || 0)))}
                  </div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button onClick={prepareRefund} disabled={refundBusy}
                  className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50">
                  {refundBusy ? "Preparing…" : "Prepare VAT311"}
                </button>
                {refundApp && (
                  <a href={api.refund311ExportUrl(current!.id)}
                    className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated">
                    Download VAT311 PDF
                  </a>
                )}
                {refundApp && (
                  <span className="text-sm text-success">
                    Prepared · net refund expected AED {money(refundApp.net_refund_expected)}
                  </span>
                )}
              </div>
            </Card>
          )}
        </>
      )}

      {/* Drill-down modal */}
      {drill && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" onClick={() => setDrill(null)}>
          <Card className="max-h-[80vh] w-full max-w-3xl overflow-hidden p-0" >
            <div className="flex items-center justify-between border-b border-border px-5 py-3">
              <h3 className="font-semibold">Box {drill.box} · {drill.label} ({drill.txns.length})</h3>
              <button onClick={() => setDrill(null)} className="text-muted hover:text-fg">✕</button>
            </div>
            <div className="max-h-[65vh] overflow-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-elevated text-muted">
                  <tr>
                    <th className="px-3 py-2 text-left">Date</th>
                    <th className="px-3 py-2 text-left">Type</th>
                    <th className="px-3 py-2 text-left">Party</th>
                    <th className="px-3 py-2 text-left">Invoice</th>
                    <th className="px-3 py-2 text-left">Treatment</th>
                    <th className="px-3 py-2 text-right">Taxable</th>
                    <th className="px-3 py-2 text-right">VAT</th>
                  </tr>
                </thead>
                <tbody>
                  {drill.txns.map((t, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="px-3 py-1.5">{t.date}</td>
                      <td className="px-3 py-1.5">{t.doc_type}</td>
                      <td className="px-3 py-1.5">{t.party}</td>
                      <td className="px-3 py-1.5">{t.invoice_number}</td>
                      <td className="px-3 py-1.5">{t.treatment}</td>
                      <td className="px-3 py-1.5 text-right">{money(t.taxable_amount)}</td>
                      <td className="px-3 py-1.5 text-right">{money(t.vat_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
