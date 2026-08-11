"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { FtaSourceRef } from "@/lib/types";
import { Card } from "@/components/ui";

interface Msg {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  vatIssue?: string | null;
  treatment?: string | null;
  effectiveDate?: string | null;
  validationStatus?: string;
  provisional?: boolean;
  sources?: FtaSourceRef[];
}

const VALIDATION_STYLE: Record<string, { label: string; cls: string }> = {
  grounded: { label: "Grounded in FTA sources", cls: "bg-success/15 text-success" },
  provisional: { label: "Provisional — SME validation required", cls: "bg-warning/15 text-warning" },
  requires_sme: { label: "Provisional — SME validation required", cls: "bg-danger/15 text-danger" },
};

interface Attachment {
  name: string;
  text: string;
  chars: number;
  ocrUsed: boolean;
  warnings: string[];
}

// Formats the assistant accepts as attachments.
const ACCEPT = ".pdf,.docx,.doc,.jpg,.jpeg,.png";

const SUGGESTIONS = [
  "Does reverse charge apply to imported SaaS subscriptions?",
  "Which VAT rate applies to exported goods, and what evidence do I need?",
  "Can I recover input VAT on staff entertainment?",
  "What are the mandatory fields of a full tax invoice?",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asOfDate, setAsOfDate] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (fileRef.current) fileRef.current.value = ""; // allow re-selecting the same file
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const res = await api.uploadAssistantDoc(file);
      setAttachment({
        name: res.filename,
        text: res.text,
        chars: res.chars,
        ocrUsed: res.ocr_used,
        warnings: res.warnings || [],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setAttachment(null);
    } finally {
      setUploading(false);
    }
  };

  const send = async (text: string) => {
    const q = text.trim();
    if ((!q && !attachment) || busy) return;
    const shown = attachment && q ? `${q}\n\n📎 ${attachment.name}` : attachment ? `📎 ${attachment.name}` : q;
    const next: Msg[] = [...messages, { role: "user", content: shown }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      // Send the real question text (not the attachment-decorated label) plus the doc.
      const payload: { role: string; content: string }[] = [
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content: q || `Please review the attached document "${attachment?.name}".` },
      ];
      const res = await api.chat(
        payload,
        attachment ? { name: attachment.name, text: attachment.text } : null,
        asOfDate || null,
      );
      setMessages([
        ...next,
        {
          role: "assistant",
          content: res.reply,
          citations: res.citations,
          vatIssue: res.vat_issue,
          treatment: res.applicable_treatment,
          effectiveDate: res.effective_date,
          validationStatus: res.validation_status,
          provisional: res.provisional,
          sources: res.fta_sources,
        },
      ]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages([...next, { role: "assistant", content: `⚠️ ${msg}` }]);
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-semibold">VAT Assistant</h1>
        <p className="text-sm text-muted">
          Ask UAE VAT questions or attach a document. Answers are grounded in the latest approved
          official FTA rules, cite the source &amp; effective date, and are labelled
          <b> Grounded</b> or <b> Provisional (SME validation required)</b>.
        </p>
      </div>

      <Card className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted">Try one of these:</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-elevated"
                  >
                    {s}
                  </button>
                ))}
              </div>
              <p className="text-xs text-muted">
                Or attach a tax invoice / contract and ask “Is this a valid UAE tax invoice?”
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] ${m.role === "user" ? "" : "w-full"}`}>
                <div
                  className={`whitespace-pre-line rounded-xl px-4 py-2.5 text-sm ${
                    m.role === "user" ? "bg-brand text-brand-fg" : "bg-elevated"
                  }`}
                >
                  {m.content}
                </div>
                {/* FTA grounding panel */}
                {m.role === "assistant" && m.validationStatus && (
                  <div className="mt-2 rounded-lg border border-border bg-surface p-3 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 font-semibold ${
                          (VALIDATION_STYLE[m.validationStatus] ?? VALIDATION_STYLE.requires_sme).cls
                        }`}
                      >
                        {(VALIDATION_STYLE[m.validationStatus] ?? VALIDATION_STYLE.requires_sme).label}
                      </span>
                      {m.vatIssue && <span className="text-muted">Issue: <b className="text-fg">{m.vatIssue}</b></span>}
                      {m.treatment && <span className="text-muted">Treatment: <b className="text-fg">{m.treatment}</b></span>}
                      {m.effectiveDate && <span className="text-muted">Effective: <b className="text-fg">{m.effectiveDate}</b></span>}
                    </div>
                    {m.sources && m.sources.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {m.sources.map((s, j) => (
                          <li key={j} className="flex flex-wrap items-baseline gap-1.5">
                            <span className="rounded bg-elevated px-1.5 py-0.5 text-[10px] font-medium text-muted">
                              {s.tier}
                            </span>
                            <span className="font-medium">{s.title}</span>
                            {s.effective_from && <span className="text-muted">· eff. {s.effective_from}</span>}
                            {s.source_ref &&
                              (s.source_ref.startsWith("http") ? (
                                <a href={s.source_ref} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                                  source ↗
                                </a>
                              ) : (
                                <span className="text-brand">{s.source_ref}</span>
                              ))}
                          </li>
                        ))}
                      </ul>
                    )}
                    {m.provisional && (
                      <div className="mt-2 text-[11px] text-muted">
                        This conclusion is not a confirmed FTA filing position — confirm against the official
                        FTA source and obtain UAE VAT SME sign-off before filing.
                      </div>
                    )}
                  </div>
                )}
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {m.citations.map((c, j) => (
                      <span
                        key={j}
                        className="rounded-md border border-border bg-surface px-2 py-0.5 text-xs text-brand"
                        title={c}
                      >
                        {c.length > 60 ? c.slice(0, 60) + "…" : c}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="text-sm text-muted">Thinking…</div>}
          <div ref={endRef} />
        </div>

        {/* Attachment chip + errors */}
        {(attachment || uploading || error) && (
          <div className="border-t border-border px-3 pt-2">
            {uploading && <div className="text-xs text-muted">Reading document…</div>}
            {error && <div className="text-xs text-danger">⚠️ {error}</div>}
            {attachment && (
              <div className="flex items-center justify-between gap-2 rounded-lg border border-border bg-elevated px-3 py-1.5 text-xs">
                <span className="truncate">
                  📎 <span className="font-medium">{attachment.name}</span>
                  <span className="text-muted">
                    {" "}
                    · {attachment.chars.toLocaleString()} chars{attachment.ocrUsed ? " · OCR" : ""}
                    {attachment.warnings.length > 0 ? ` · ⚠️ ${attachment.warnings[0]}` : ""}
                  </span>
                </span>
                <button
                  onClick={() => setAttachment(null)}
                  className="shrink-0 rounded px-1.5 text-muted hover:text-fg"
                  aria-label="Remove attachment"
                >
                  ✕
                </button>
              </div>
            )}
          </div>
        )}

        {/* Applicable-date control: answer under the rule in force on a transaction date */}
        <div className="flex items-center gap-2 border-t border-border px-3 pt-2 text-xs text-muted">
          <span>Applicable as of:</span>
          <input
            type="date"
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
            className="rounded-lg border border-border bg-surface px-2 py-1 text-xs"
            title="Answer using the VAT rule in force on this date (defaults to today)"
          />
          {asOfDate ? (
            <button onClick={() => setAsOfDate("")} className="text-brand hover:underline">today</button>
          ) : (
            <span>today</span>
          )}
          <span className="hidden sm:inline">— use a past date to get the treatment for that tax period.</span>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-center gap-2 border-t border-border p-3"
        >
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            onChange={onPickFile}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading || busy}
            title="Attach a document (PDF, Word, JPG/JPEG, PNG)"
            aria-label="Attach a document"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border text-muted hover:text-fg disabled:opacity-50"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
              <path d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3 3 0 014.24 4.24l-9.2 9.19a1 1 0 01-1.41-1.41l8.49-8.49" />
            </svg>
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={attachment ? "Ask about the attached document…" : "Ask a UAE VAT question…"}
            className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <button
            type="submit"
            disabled={busy || uploading}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </Card>
      <p className="mt-2 text-xs text-muted">
        Accepts PDF, Word (.docx/.doc) and images (.jpg, .jpeg, .png). Scanned files are OCR’d.
        Requires an AI provider key for grounded answers.
      </p>
    </div>
  );
}
